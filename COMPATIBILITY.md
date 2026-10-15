# Limites, restauração e atualizações

Esta é uma versão beta para Windows x64. Os testes de portabilidade usam uma instalação simulada; não substituem um teste visual em outro computador ou uma autorização da Valve. Compatibilidade com versões futuras do Dota não é garantida.

## Arquivos alterados pela ativação

O Atelier adiciona VPKs na camada de idioma de áudio selecionada: `game/dota_<idioma>/pakNN_dir.vpk` para heróis e `game/dota_<idioma>/maps/dota.vpk` para o terreno. A alocação de cada herói é fixa. Com áudio em inglês, usa a camada russa se ela estiver disponível sem pacote de vozes russo instalado. A alteração em `game/dota/cfg/boot.vcfg` limita-se ao valor `AudioLanguage`; `UILanguage` é preservado.

O programa não grava em executáveis, DLLs, assinaturas, `gameinfo.gi`, opções de inicialização, configurações do Steam ou inventário. Não injeta código, não lê memória do jogo e não pede credenciais Steam. Consulta o Registro apenas para localizar a instalação Steam. Há uma única instância por sessão Windows; a troca exige o Dota fechado. Não existe um serviço ou tarefa agendada.

As skins admitem recursos cosméticos e, excepcionalmente, `scripts/npc/portraits.txt` como dado de câmera. Nas montagens novas, a alteração desse arquivo deve ficar limitada ao bloco do herói selecionado. Scripts executáveis, tabelas de itens, interfaces Panorama executáveis, mapas dentro de pacotes de skin e instaladores de terceiros são rejeitados. CRC, hashes e dependências são verificações estruturais; não certificam a aparência nem a segurança de todo recurso compilado.

## Como desfazer

Desative cada visual pelo próprio app, com o Dota fechado. Ao desativar o último, o Atelier restaura o arquivo de áudio original byte a byte e os arquivos previamente existentes, ou remove os VPKs que ele próprio adicionou. Backups e registros ficam em `%LOCALAPPDATA%\DotaAtelier`.

Antes de escrever, o app confere o conteúdo atual. Uma operação incompleta pode ser recuperada pelo botão de recuperação. Se um arquivo mudou externamente, o app bloqueia a escrita para preservar a alteração externa; isso pode exigir análise manual. Os backups precisam continuar presentes e íntegros: não apague a pasta de dados, não copie a sessão de outro PC e não use ferramentas de limpeza enquanto houver visuais ativos. O app não tenta desfazer uma atualização oficial do Steam.

## Atualizações do Dota

O atualizador funciona enquanto o Atelier está aberto e o Dota fechado. Aguarda o Steam indicar instalação concluída, verifica a estabilidade dos arquivos de origem e reconstrói os terrenos a partir do mapa padrão e do terreno oficial encontrados naquele PC. Um terreno ativo é reaplicado quando a montagem muda. Se a estrutura esperada do mapa deixar de existir, a atualização para com erro, sem publicar uma montagem incompatível.

Arcanas vêm de ZIPs de uma revisão fixa do projeto Dota2PornFxWeb. O download exige tamanho, SHA-256 e hash Git exatos. Recursos necessários são selecionados por receita e complementados com dados oficiais locais. Uma atualização dos VPKs oficiais invalida a montagem em cache: na próxima ativação, o app prepara novamente usando o ZIP validado em cache ou baixa a fonte se necessário. O app não altera automaticamente uma skin que já está ativa para trocar de versão da fonte comunitária.

Reconstruir a montagem não converte automaticamente modelos para formatos futuros do motor. Se as dependências, o retrato ou os modelos da fonte ficarem incompatíveis, será necessária uma receita revisada e uma nova versão do Atelier. O app não troca silenciosamente os hashes fixados por um download mais recente.

## Levar a outro PC

Use somente o ZIP portátil da página Releases e extraia a pasta inteira. São necessários Windows x64, Dota instalado e iniciado ao menos uma vez, acesso à pasta do jogo e internet no primeiro download de cada skin. Não é necessário Python. Se a instalação exigir privilégios de gravação indisponíveis, a ativação falha; o app não eleva privilégios automaticamente.

Não transfira `%LOCALAPPDATA%\DotaAtelier`, VPKs preparados, backups ou registros da sua sessão como se fossem um instalador. Cada PC detecta sua instalação, gera seus terrenos e prepara suas skins. O release não contém VPKs, dados pessoais, credenciais, sessões ou caminhos da máquina de desenvolvimento.

## Steam e VAC

Mesmo sem alterar componentes de segurança, sobrepor recursos do cliente é uma modificação do jogo. Não há certificação Valve/VAC nem garantia de que seja permitida em partidas online ou aceita após uma atualização. Os [termos do Steam](https://store.steampowered.com/subscriber_agreement/) tratam de modificações não autorizadas. O projeto não promete risco zero de bloqueio, punição, falha visual ou rejeição pelo cliente.

## Verificação reproduzível

Com Python 3.11 e as dependências de build instaladas:

```powershell
python -m unittest test_portability test_updater -v
python build_share.py
```

Os testes públicos criam arquivos sintéticos em diretórios temporários, não acessam contas e não modificam uma instalação real de Dota. Cobrem instalação limpa, alterações limitadas aos caminhos previstos, restauração byte a byte, preservação de alterações externas, recuperação de transação, falha de gravação, invalidação de cache, ZIP inseguro, download divergente dos hashes, fontes alteradas durante montagem e atualização de terrenos.
