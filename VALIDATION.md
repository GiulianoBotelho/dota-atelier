# Validação de cosméticos — 0.2.1-beta.1

Auditoria executada em 15/10/2026 com os arquivos oficiais da instalação de referência. As 28 variantes passaram pela montagem, CRC, dependências e comparação dos bytes dos modelos associados a cada slot. Os ZIPs de origem permaneceram fixados pelos hashes publicados.

**Isto não equivale a validar 100% da aparência no Dota.** Todas as linhas abaixo ainda precisam de conferência visual no jogo com o equipamento real do usuário, incluindo animações, habilidades, partículas dos itens e variantes. Personas não são convertidas; modelos genéricos ou compartilhados entre heróis são preservados.

## Falha tratada

A montagem anterior substituía principalmente os modelos padrão, enquanto cosméticos convencionais já equipados podiam continuar visíveis e se misturar com a arcana. A revisão 2 consulta a tabela oficial de itens somente em leitura, resolve os slots e estilos e associa cada modelo compatível à mesma peça esperada no loadout padrão do pacote. Slots vazios usam o modelo invisível oficial como conteúdo local; esse recurso genérico nunca é substituído globalmente.

A auditoria confirma que cada alias gerado contém exatamente os mesmos bytes do modelo canônico do seu slot. O inventário e a tabela oficial de itens não são gravados. Os VPKs resultantes continuam restritos a recursos cosméticos e ao dado de retrato permitido.

## Resultado por variante

| Herói / variante | Modelos compatibilizados | Recursos | Montagem e dependências | Visual no jogo |
|---|---:|---:|---|---|
| Vengeful Spirit | 78 | 910 | Passou | Pendente |
| Skywrath Mage | 117 | 189 | Passou | Pendente |
| Razor | 80 | 169 | Passou | Pendente |
| Faceless Void | 90 | 122 | Passou | Pendente |
| Drow Ranger | 218 | 255 | Passou | Pendente |
| Spectre | 80 | 118 | Passou | Pendente |
| Windranger | 127 | 201 | Passou | Pendente |
| Queen of Pain | 105 | 1207 | Passou | Pendente |
| Wraith King | 138 | 475 | Passou | Pendente |
| Earthshaker | 83 | 176 | Passou | Pendente |
| Ogre Magi | 60 | 171 | Passou | Pendente |
| Rubick | 107 | 126 | Passou | Pendente |
| Pudge | 218 | 328 | Passou | Pendente |
| Juggernaut | 146 | 182 | Passou | Pendente |
| Monkey King | 42 | 51 | Passou | Pendente |
| Io | 3 | 254 | Passou | Pendente |
| Zeus | 45 | 90 | Passou | Pendente |
| Crystal Maiden | 121 | 149 | Passou | Pendente |
| Phantom Assassin | 133 | 182 | Passou | Pendente |
| Shadow Fiend | 38 | 68 | Passou | Pendente |
| Techies | 54 | 76 | Passou | Pendente |
| Terrorblade | 34 | 54 | Passou | Pendente |
| Legion Commander | 154 | 182 | Passou | Pendente |
| Lina | 104 | 141 | Passou | Pendente |
| Axe | 162 | 176 | Passou | Pendente |
| Tidehunter / megalodon | 99 | 148 | Passou | Pendente |
| Tidehunter / hammerhead | 99 | 147 | Passou | Pendente |
| Tidehunter / hunger | 99 | 139 | Passou | Pendente |

## Reprodução da auditoria

Com uma instalação própria do Dota e as dependências do projeto:

```powershell
python audit_catalog.py --game "CAMINHO_DA_INSTALACAO\game"
```

O comando prepara as variantes em `build/audit-cache` e gera `build/catalog-audit.json`; não ativa mods nem escreve na instalação do Dota. Pode baixar todos os ZIPs do catálogo e consumir espaço para os pacotes de teste.

Os testes sintéticos de parser, estilos, prefabs, modelos compartilhados, caches, restauração e recuperação são executados separadamente no GitHub Actions. Eles não substituem a confirmação visual do usuário.
