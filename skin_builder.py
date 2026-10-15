"""Fetch, validate and assemble one local cosmetic VPK from a pinned public catalog."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile

from tide_trial import sha
from vpk_lab import index, read_entry, read_single, references, write_single


MAX_ZIP_BYTES = 120 * 1024 * 1024
MAX_VPK_BYTES = 512 * 1024 * 1024
MAX_RESOURCE_COUNT = 50000
VPK_SUFFIXES = {".vmdl_c", ".vtex_c", ".vmat_c", ".vpcf_c", ".vsndevts_c",
                ".vsnd_c", ".vanim_c", ".vmesh_c", ".vagrp_c", ".vseq_c",
                ".vsnap_c", ".vphys_c", ".vents_c", ".vwnod_c", ".vrman_c"}


class SkinBuilder:
    def __init__(self, game, library, manifest_path=None):
        self.game = Path(game).resolve()
        self.library = Path(library).resolve()
        self.cache = self.library / "download-cache"
        self.skin_dir = self.library / "skins"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.skin_dir.mkdir(parents=True, exist_ok=True)
        if manifest_path is None:
            assets = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"
            manifest_path = assets / "skin-recipes.json"
        self.manifest_path = Path(manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text("utf-8"))
        if self.manifest.get("schema_version") != 1:
            raise ValueError("Catálogo de pacotes de skins incompatível.")
        self._game_indexes = None

    @staticmethod
    def _git_blob_sha1(data: bytes) -> str:
        return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

    def _download_zip(self, recipe, progress):
        commit = self.manifest.get("source_commit", "")
        path = recipe.get("source_zip", "")
        parts = PurePosixPath(path).parts
        if (len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)
                or not parts or parts[0] != "assets" or ".." in parts
                or not path.startswith("assets/files/heroes/")):
            raise ValueError("Origem do pacote não passou na validação do catálogo.")
        expected_size = int(recipe.get("source_size", 0))
        expected_git = recipe.get("source_git_blob_sha1", "")
        expected_sha = recipe.get("source_sha256", "")
        if not 1 <= expected_size <= MAX_ZIP_BYTES:
            raise ValueError("Tamanho da origem fora do limite permitido.")
        if (len(expected_git) != 40 or len(expected_sha) != 64
                or any(c not in '0123456789abcdef' for c in expected_git + expected_sha)):
            raise ValueError("Hash de origem ausente ou inválido.")
        destination = self.cache / (expected_sha + ".zip")
        if destination.is_file():
            data = destination.read_bytes()
            if (len(data) == expected_size and self._git_blob_sha1(data) == expected_git
                    and hashlib.sha256(data).hexdigest() == expected_sha):
                return destination
            destination.unlink(missing_ok=True)

        url = ("https://raw.githubusercontent.com/h6rd/Dota2PornFxWeb/" + commit + "/"
               + quote(path, safe="/"))
        progress("Baixando o pacote público da arcana…")
        request = Request(url, headers={"User-Agent": "DotaAtelier/1.0", "Accept": "application/octet-stream"})
        fd, temporary_name = tempfile.mkstemp(prefix="skin-download-", suffix=".tmp", dir=self.cache)
        temporary = Path(temporary_name)
        size = 0
        digest = hashlib.sha256()
        git_hash = hashlib.sha1()
        try:
            with os.fdopen(fd, "wb") as target, urlopen(request, timeout=90) as response:
                git_hash.update(b"blob " + str(expected_size).encode("ascii") + b"\0")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > expected_size:
                        raise ValueError("O download excede o tamanho publicado no catálogo.")
                    target.write(chunk)
                    digest.update(chunk)
                    git_hash.update(chunk)
            if (size != expected_size or digest.hexdigest() != expected_sha
                    or git_hash.hexdigest() != expected_git):
                raise ValueError("O pacote baixado não corresponde aos hashes publicados.")
            os.replace(temporary, destination)
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    def _extract_vpk(self, archive_path, folder):
        with ZipFile(archive_path) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if sum(info.file_size for info in files) > MAX_VPK_BYTES:
                raise ValueError("O ZIP contém mais dados do que o limite permitido.")
            candidates = []
            for info in files:
                name = info.filename.replace("\\", "/")
                parts = PurePosixPath(name).parts
                if (PurePosixPath(name).is_absolute() or ".." in parts or ":" in name
                        or ((info.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError("O arquivo público contém um caminho inseguro.")
                if name.casefold().endswith(".vpk"):
                    candidates.append(info)
            if len(candidates) != 1:
                raise ValueError("O arquivo público não contém exatamente um VPK.")
            info = candidates[0]
            if not 12 <= info.file_size <= MAX_VPK_BYTES:
                raise ValueError("Tamanho de VPK inválido.")
            output = folder / "source.vpk"
            with archive.open(info) as source, output.open("wb") as target:
                copied = shutil.copyfileobj(source, target, length=1024 * 1024)
            if output.stat().st_size != info.file_size:
                raise ValueError("VPK truncado dentro do ZIP.")
            return output

    def _official_context(self):
        if self._game_indexes is not None:
            return self._game_indexes
        candidates = [self.game / "dota/pak01_dir.vpk", self.game / "core/pak01_dir.vpk"]
        self._game_indexes = [(path, index(path)) for path in candidates if path.is_file()]
        if not any(path == self.game / "dota/pak01_dir.vpk" for path, _ in self._game_indexes):
            raise ValueError("Não encontrei o VPK principal do Dota nesta instalação.")
        return self._game_indexes

    def _official_entry(self, resource):
        for path, context in self._official_context():
            try:
                return read_entry(path, resource, context)
            except (KeyError, OSError, ValueError):
                continue
        raise ValueError("O recurso oficial necessário não existe nesta instalação: " + resource)

    def _hero_entries(self, recipe, source):
        resources = recipe.get("resources", [])
        aliases = recipe.get("aliases", {})
        if not resources or len(resources) > MAX_RESOURCE_COUNT:
            raise ValueError("Lista de recursos da arcana inválida.")
        entries = {}
        for resource in resources:
            if not isinstance(resource, str) or ".." in PurePosixPath(resource).parts or "\\" in resource or ":" in resource:
                raise ValueError("Caminho de recurso inválido no catálogo.")
            if resource in aliases:
                continue
            if resource not in source:
                raise ValueError("O pacote público não contém o recurso esperado: " + resource)
            entries[resource] = source[resource]
        for target, alias in aliases.items():
            if target not in resources:
                raise ValueError("Alias fora da lista permitida.")
            if alias.startswith("Official empty particle"):
                payload = self._official_entry("particles/error/null.vpcf_c")
            elif alias.startswith("Official invisible model"):
                payload = self._official_entry("models/development/invisiblebox.vmdl_c")
            else:
                if alias not in source:
                    raise ValueError("O recurso de origem de um alias está ausente.")
                payload = source[alias]
            entries[target] = payload
        return entries

    @staticmethod
    def _replace_hero_block(data, source_model, hero_model):
        from manager import _kv_block_span
        src_start, src_end = _kv_block_span(data, source_model)
        dst_start, dst_end = _kv_block_span(data, hero_model)
        block = data[src_start:src_end]
        source_key = ('"' + source_model + '"').encode('utf-8')
        target_key = ('"' + hero_model + '"').encode('utf-8')
        if not block.startswith(source_key):
            raise ValueError('A chave do modelo de retrato não corresponde ao bloco selecionado.')
        block = target_key + block[len(source_key):]
        patched = data[:dst_start] + block + data[dst_end:]
        check_start, check_end = _kv_block_span(patched, hero_model)
        if (patched[check_start:check_end] != block
                or patched[:check_start] != data[:dst_start]
                or patched[check_end:] != data[dst_end:]):
            raise ValueError("A alteração do retrato não ficou limitada ao Tidehunter.")
        return patched

    def _style_entries(self, recipe, source):
        resources = recipe.get("allowlist", [])
        if not resources or len(resources) > MAX_RESOURCE_COUNT:
            raise ValueError("Lista de recursos do estilo inválida.")
        blocked = set(recipe.get("blocked_resources", []))
        entries = {}
        icon_target = "panorama/images/heroes/selection/npc_dota_hero_tidehunter_png.vtex_c"
        icon_source = recipe.get("selection_icon_from")
        for resource in resources:
            if resource in blocked:
                raise ValueError("Recurso bloqueado incluído na lista de montagem.")
            if resource == icon_target and icon_source:
                entries[resource] = self._official_entry(icon_source)
            elif resource in source:
                entries[resource] = source[resource]
            else:
                raise ValueError("O pacote público não contém o recurso esperado: " + resource)
        portrait = self._official_entry("scripts/npc/portraits.txt")
        entries["scripts/npc/portraits.txt"] = self._replace_hero_block(
            portrait,
            recipe["portrait_model"],
            "models/heroes/tidehunter/tidehunter.vmdl",
        )
        return entries

    def _validate_references(self, entries):
        available = set(entries)
        for _path, (_base, indexed) in self._official_context():
            available.update(indexed)
        missing = set()
        for resource, payload in entries.items():
            if not resource.endswith((".vmdl_c", ".vmat_c", ".vpcf_c")):
                continue
            for reference in references(payload):
                if reference not in available and reference + "_c" not in available:
                    missing.add(reference)
        if missing:
            first = sorted(missing)[:8]
            raise ValueError("A versão instalada do Dota não tem dependências desta arcana: " + ", ".join(first))

    def prepare(self, hero, skin_id, progress=lambda _message: None):
        style = hero == "tidehunter"
        recipe = (self.manifest.get("styles", {}).get(skin_id) if style
                  else self.manifest.get("heroes", {}).get(hero))
        if recipe is None or recipe.get('id') != skin_id:
            raise ValueError("Esta arcana ainda não tem uma receita de montagem.")
        progress("Conferindo a origem pública e os arquivos locais do Dota…")
        downloaded = self._download_zip(recipe, progress)
        self._game_indexes = None
        official_paths = [self.game / relative for relative in ('dota/pak01_dir.vpk', 'core/pak01_dir.vpk')
                          if (self.game / relative).is_file()]
        def source_stamps():
            return {str(path): (path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                    for path in official_paths}
        initial_stamps = source_stamps()
        official_sources = {path.relative_to(self.game).as_posix(): sha(path.read_bytes())
                            for path in official_paths}
        with tempfile.TemporaryDirectory(prefix="skin-build-", dir=self.cache) as temporary:
            folder = Path(temporary)
            source_path = self._extract_vpk(downloaded, folder)
            source_entries = read_single(source_path)
            entries = self._style_entries(recipe, source_entries) if style else self._hero_entries(recipe, source_entries)
            if not entries or len(entries) > MAX_RESOURCE_COUNT:
                raise ValueError("O pacote montado está vazio ou excede o limite de recursos.")
            self._validate_references(entries)
            progress("Montando e verificando o VPK local…")
            temporary_vpk = folder / "prepared.vpk"
            write_single(temporary_vpk, entries)
            from manager import validate_vpk
            validate_vpk(temporary_vpk, "skin", hero=hero, game_path=self.game)
            if initial_stamps != source_stamps() or any(
                    sha((self.game / relative).read_bytes()) != expected
                    for relative, expected in official_sources.items()):
                raise ValueError('O Dota atualizou durante a montagem. Aguarde o Steam e tente novamente.')
            digest = sha(temporary_vpk.read_bytes())
            destination = self.skin_dir / (digest + ".vpk")
            if destination.exists():
                if sha(destination.read_bytes()) != digest:
                    raise ValueError("O pacote local já existente foi alterado.")
            else:
                os.replace(temporary_vpk, destination)
        source_url = "https://github.com/h6rd/Dota2PornFxWeb/tree/" + self.manifest["source_commit"] + "/" + recipe["source_zip"]
        return {
            "hero": hero,
            "id": skin_id,
            "sha256": digest,
            "resources": len(entries),
            "local_file": "skins/" + digest + ".vpk",
            "package_path": str(destination),
            "source_url": source_url,
            "source_commit": self.manifest["source_commit"],
            "source_sha256": recipe["source_sha256"],
            "game_path": str(self.game),
            "official_sources": official_sources,
            "status": "Pacote público baixado, filtrado e validado localmente.",
        }
