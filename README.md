# Dota Atelier

Gerenciador local para terrenos e pacotes cosméticos de Dota 2. O aplicativo portátil detecta bibliotecas Steam no Windows e permite escolher a pasta `game` manualmente. Não requer Python no computador de quem recebe o ZIP.

**Versão beta para Windows x64.** [Baixar a versão portátil](https://github.com/GiulianoBotelho/dota-atelier/releases). O projeto modifica recursos do cliente e não possui certificação Valve/VAC. A revisão técnica confirma os limites descritos abaixo, sem prometer ausência de risco em partidas online.

## Começar

1. Extraia `Dota Atelier` por inteiro para uma pasta local.
2. Abra `DotaAtelier.exe`.
3. Se o Dota não for detectado, escolha a pasta `game` da instalação. O app confere `dota\\gameinfo.gi`, os mapas oficiais e a configuração antes de aceitar o caminho.
4. Na aba **Terrenos**, o app gera os 12 mapas a partir dos VPKs oficiais encontrados naquela instalação. A geração é local e se repete quando os arquivos oficiais mudam.
5. Na aba **Arcanas**, selecione o herói e clique em **Baixar e ativar arcana**. No primeiro uso, o Atelier baixa a fonte pública daquela skin, confere os hashes publicados, filtra os recursos permitidos e monta o pacote local. Depois, a mesma arcana pode ser ativada ou desativada sem novo download.

O catálogo mostra 25 arcanas e o conjunto Immortal Axe Unleashed; Tidehunter tem três opções de estilo. O primeiro pacote de cada skin é baixado sob demanda do projeto comunitário Dota2PornFxWeb, em uma revisão fixada no catálogo do Atelier. O programa verifica tamanho e hashes SHA-256 e Git antes de abrir o ZIP; depois aceita somente um VPK e os recursos listados para aquele herói. A montagem usa os recursos oficiais encontrados na instalação local do Dota para aliases e dependências. O ZIP compartilhável contém as imagens e receitas, mas nenhum VPK cosmético.

## Como as skins são preparadas

O Dota contém recursos oficiais dos itens nos seus VPKs, mas não contém a montagem de substituição de cada mod. Os pacotes comunitários incluem modelos compilados e adaptados para substituir o herói base. Só copiar o modelo oficial de arcana para outro caminho não produz essa montagem e pode deixar peças, retrato ou efeitos incorretos. Por isso, o Atelier baixa e filtra uma fonte comunitária conhecida em vez de tentar inferir uma montagem a partir dos arquivos oficiais.

O VPK montado fica em `%LOCALAPPDATA%\\DotaAtelier\\skins`. O Atelier verifica CRC, limites, extensões de recurso, dependências e dados de retrato antes de aplicar o pacote. Rejeita scripts executáveis, configurações e tabelas de itens; a única exceção na pasta `scripts` é o dado de câmera `scripts/npc/portraits.txt`, limitado ao bloco do herói. Se os VPKs oficiais usados na montagem mudarem, o cache é invalidado e a próxima ativação prepara novamente a skin. Um pacote aceito estruturalmente ainda precisa ser conferido no jogo; um novo formato de modelo pode exigir uma nova receita e uma atualização do app.

Fonte pública de montagem: [Dota2PornFxWeb](https://github.com/h6rd/Dota2PornFxWeb). O botão **Catálogo público** abre o repositório de origem. O app não executa instaladores de terceiros.

Desde a versão 0.2.1, a montagem lê a tabela oficial de itens para substituir visualmente também os cosméticos convencionais já equipados, pelo modelo esperado de cada slot. Essa tabela não é alterada nem incluída no VPK. Modelos genéricos ou compartilhados entre heróis são preservados. Personas ficam fora dessa compatibilização; partículas de itens e todas as combinações possíveis ainda precisam de conferência no jogo. Veja o [relatório de validação por herói](VALIDATION.md).

## Atualizar o aplicativo

Feche o Atelier, baixe **DotaAtelier-Compartilhar.zip** da release nova e extraia a pasta inteira. Abra o novo **DotaAtelier.exe** junto da sua pasta `_internal`. Não substitua somente o executável. Backups e sessão permanecem em `%LOCALAPPDATA%\\DotaAtelier`; não apague nem transfira essa pasta entre PCs.

Na versão 0.2.1, as montagens antigas precisam ser refeitas. Se uma arcana já estiver ativa, use **Atualizar arcana**, com o Dota fechado, para aplicar a montagem nova. Apenas atualizar o aplicativo não troca automaticamente o VPK que já está ativo.

## O que o app altera

Para ativar um visual, o Atelier instala um VPK extra na camada de idioma de áudio do Dota. Quando o áudio está em inglês, a montagem atual usa a camada russa e registra a mudança de `AudioLanguage` em `dota/cfg/boot.vcfg`; a interface (`UILanguage`) é preservada. Desativar o último visual restaura o arquivo original byte a byte.

O app não altera `gameinfo.gi`, `gameinfo_branchspecific.gi`, assinaturas, executáveis, DLLs, configurações do Steam, opções de inicialização ou inventário. A troca é bloqueada enquanto `dota2.exe` estiver aberto. Isso descreve os limites implementados; não é uma certificação da Valve nem uma promessa de aceitação pelo VAC. A Valve proíbe modificações não autorizadas nos termos do Steam, então não há como garantir risco zero ao usar mods no cliente online. Veja o [Steam Subscriber Agreement](https://store.steampowered.com/subscriber_agreement/).

Terrenos e cosméticos são reversíveis enquanto os backups estiverem íntegros e os arquivos não tiverem sido alterados externamente. Registros e cópias de segurança ficam em `%LOCALAPPDATA%\\DotaAtelier`. Não remova essa pasta enquanto houver visual ativo; use **Desativar** para restaurar os arquivos primeiro. Um conflito externo bloqueia a escrita e pode exigir análise manual.

Leia [limites, restauração, atualizações e requisitos de outro PC](COMPATIBILITY.md). Transfira somente o ZIP portátil; cada PC prepara seus próprios arquivos. Não copie seus backups, sessões ou a pasta de dados do Atelier para outra pessoa.

## Compartilhar ou compilar

O ZIP portátil para outras pessoas é produzido por:

```powershell
python build_share.py
```

O processo cria `dist/DotaAtelier-Compartilhar.zip` e `dist/DotaAtelier-Fonte.zip`. Ele inclui o aplicativo, o catálogo de receitas e as imagens de prévia atribuídas, mas exclui todos os VPKs de cosméticos e de mapas. Cada pessoa gera os terrenos do próprio Dota; pacotes cosméticos são baixados e preparados sob demanda no primeiro uso. O ZIP de fonte omite também downloads, ferramentas auxiliares e arquivos temporários.

Arquivos `.sha256` acompanham os dois ZIPs para conferir se chegaram intactos.

Para compilar, instale Python 3.11 e execute:

```powershell
python -m pip install -r requirements-build.txt
python -m unittest test_portability test_updater test_cosmetic_schema -v
python build_share.py
```

Os testes públicos usam arquivos sintéticos e não modificam o Dota instalado. O build não exige os VPKs da máquina de desenvolvimento. O binário publicado não possui assinatura Authenticode comercial.

## Créditos e licença

Este repositório é distribuído sob [GPL-3.0](LICENSE). Os dados do catálogo e prévias vieram do projeto comunitário [Dota2PornFxWeb](https://github.com/h6rd/Dota2PornFxWeb), publicado como GPL-3.0. As marcas e conteúdos de Dota 2 pertencem aos respectivos titulares; a licença do código não transfere direitos sobre conteúdo do jogo. O Atelier não é afiliado à Valve. Licenças do Python, PyInstaller, Pillow e Tcl/Tk, além da referência MIT do ValveResourceFormat, acompanham os arquivos em `licenses/` e `THIRD_PARTY_LICENSES.txt`.
