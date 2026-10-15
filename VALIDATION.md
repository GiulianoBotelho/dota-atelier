# Validação de cosméticos — 0.2.2-beta.1

Revisão executada em 15/10/2026 com os arquivos oficiais da instalação de referência. As 28 variantes passaram por montagem, CRC, existência de dependências e verificação de ciclos entre modelos, inclusive dependências obtidas dos VPKs oficiais. Foram executados 40 testes automatizados sintéticos.

**A versão 0.2.1 continua com defeitos relatados no jogo:** mistura de peças equipadas, Spectre com aparência inesperada e Wraith King com ataques anormais depois do crítico. Os testes anteriores validavam arquivos e não reproduziam esses defeitos. A nova montagem ainda precisa dessa confirmação visual; nenhuma linha está marcada como aprovada no Dota.

## Alterações demonstradas nesta revisão

- Wraith King: corpo e seis peças vêm dos modelos oficiais da arcana encontrados no Dota instalado. Os bytes de cada modelo são comparados com a origem local na auditoria. São preservadas as animações compiladas atuais, sem recompilar nem editar suas sequências. Os modelos, materiais e partículas antigos da fonte comunitária deixam de fazer parte desse pacote; apenas imagens de interface são aproveitadas. Isto trata a divergência de arquivos, mas o defeito após o crítico ainda não foi reproduzido e confirmado como resolvido no jogo.
- Tabela de itens consultada somente em leitura: cobertura de modificadores `model`, inclusive quando um item troca a peça de outro slot. A peça segue o slot do recurso substituído.
- Modelos referenciados por outros modelos são preservados. Na Crystal Maiden, substituir o modelo da arcana pelo corpo que o inclui criava uma dependência circular; a montagem agora preserva esse include e rejeita ciclos em qualquer herói.
- Importações antigas não mascaram mais um cache de montagem invalidado. A interface exige nova preparação em vez de reativar silenciosamente o VPK legado.
- A revisão de montagem passa a 3; caches anteriores são invalidados. A atualização do aplicativo não aplica automaticamente novos VPKs ao jogo.

## Limitações observadas

O arquivo visual não altera os modificadores de atividade, estilo, grupos de corpo e partículas definidos pelo equipamento real da conta. Converter caminhos de modelos não garante compatibilidade com todas essas combinações. Se houver mistura, usar o conjunto padrão é um teste de diagnóstico; isto não deve ser anunciado como funcionamento completo com qualquer inventário. Personas e modelos compartilhados continuam fora da conversão.

A auditoria de aliases demonstra igualdade de bytes com a peça escolhida pela receita, não que a escolha renderize corretamente. Inspeção de sequências usa o [Source 2 Viewer / ValveResourceFormat](https://s2v.app/ValveResourceFormat/guides/format-support.html); dumps não substituem reprodução no Dota. Não houve teste visual interativo de todos os heróis nesta revisão.

## Resultado por variante

| Herói / variante | Aliases verificados | Recursos | Montagem / dependências / ciclos | Visual no jogo |
|---|---:|---:|---|---|
| Vengeful Spirit | 117 | 949 | Passou | Pendente |
| Skywrath Mage | 118 | 190 | Passou | Pendente |
| Razor | 86 | 175 | Passou | Pendente |
| Faceless Void | 120 | 152 | Passou | Pendente |
| Drow Ranger | 272 | 306 | Passou | Pendente |
| Spectre | 80 | 118 | Passou | Pendente |
| Windranger | 189 | 262 | Passou | Pendente |
| Queen of Pain | 142 | 1244 | Passou | Pendente |
| Wraith King | 140 | 158 | Passou | Pendente |
| Earthshaker | 124 | 216 | Passou | Pendente |
| Ogre Magi | 77 | 188 | Passou | Pendente |
| Rubick | 108 | 127 | Passou | Pendente |
| Pudge | 254 | 364 | Passou | Pendente |
| Juggernaut | 151 | 187 | Passou | Pendente |
| Monkey King | 48 | 57 | Passou | Pendente |
| Io | 3 | 254 | Passou | Pendente |
| Zeus | 46 | 91 | Passou | Pendente |
| Crystal Maiden | 120 | 148 | Passou | Pendente |
| Phantom Assassin | 137 | 186 | Passou | Pendente |
| Shadow Fiend | 41 | 71 | Passou | Pendente |
| Techies | 54 | 76 | Passou | Pendente |
| Terrorblade | 35 | 55 | Passou | Pendente |
| Legion Commander | 157 | 185 | Passou | Pendente |
| Lina | 104 | 141 | Passou | Pendente |
| Axe | 162 | 176 | Passou | Pendente |
| Tidehunter / megalodon | 151 | 200 | Passou | Pendente |
| Tidehunter / hammerhead | 151 | 199 | Passou | Pendente |
| Tidehunter / hunger | 151 | 191 | Passou | Pendente |

## Reprodução da auditoria

Com uma instalação própria do Dota e as dependências do projeto:

```powershell
python audit_catalog.py --game "CAMINHO_DA_INSTALACAO\game"
```

O comando prepara as variantes em `build/audit-cache` e gera `build/catalog-audit.json`; não ativa mods nem escreve na instalação do Dota. Pode baixar todos os ZIPs do catálogo e consumir espaço para os pacotes de teste.

Os testes sintéticos de parser, estilos, prefabs, modelos compartilhados, caches, restauração e recuperação são executados separadamente no GitHub Actions. Eles não substituem a confirmação visual do usuário.
