# Alterações

## 0.2.2-beta.1 — 2026-10-15

- Wraith King montado com corpo e peças oficiais locais, incluindo as animações atuais; dependências comunitárias antigas removidas dessa receita. Correção visual após o crítico ainda requer reprodução no Dota.
- Cobertura de trocas de modelo por modificadores de itens e por outros slots.
- Includes de animação preservados e ciclos entre modelos rejeitados, incluindo o caso da Crystal Maiden.
- VPKs importados legados não são mais reativados como fallback de uma montagem invalidada.
- Montagem revisão 3, auditoria das 28 variantes e 40 testes. Limitações de equipamento e ausência de validação visual explicitadas na interface e no relatório.

## 0.2.1-beta.1 — 2026-10-15

- Corrigida a mistura entre a arcana e cosméticos convencionais já equipados: leitura local da tabela de itens e substituição visual por slot, sem gravar inventário ou tabelas do jogo.
- Proteção de modelos genéricos e de caminhos compartilhados por vários heróis; personas não são convertidas.
- Correção dos caminhos-base de Drow, Shadow Fiend e Crystal Maiden.
- Correção da validação de snapshots de partículas e eventos de voz em pacotes remontados, mantendo a rejeição de scripts e tabelas de itens.
- Revisão e assinatura de receita invalidam montagens antigas; botão Atualizar arcana disponível para pacotes legados ativos.
- VPKs reutilizam os bytes de modelos idênticos para evitar duplicar cada peça para todos os cosméticos.
- Auditoria de todas as 28 variantes e novos testes de modelos equipados, estilos, prefabs, caches e modelos compartilhados. Conferência visual no jogo continua necessária; nenhuma garantia de 100% de todas as combinações é anunciada.

## 0.2.0-beta.1 — 2026-10-15

- Distribuição portátil Windows x64, sem VPKs, sessões, backups ou caminhos da máquina de desenvolvimento.
- Download sob demanda de skins com revisão fixa, limite de tamanho, SHA-256, hash Git, filtro de recursos e validação local.
- Três variantes de Tidehunter, demais arcanas do catálogo e Axe Unleashed.
- Terrenos reconstruídos com arquivos oficiais do PC; corrigida a geração em instalação limpa mesmo quando os hashes coincidem com o catálogo distribuído.
- Cache de arcanas invalidado quando os VPKs oficiais mudam; montagem interrompida quando o Steam altera os arquivos durante a preparação.
- Segunda instância bloqueada e slots fixos para os heróis, independentes da ordem do catálogo.
- Restauração byte a byte e recuperação de transação verificadas com arquivos sintéticos.
- Limites de reversibilidade, atualização e aceitação pelo Steam/VAC documentados em COMPATIBILITY.md.

Versão experimental. Testes estruturais e simulação de portabilidade não certificam a aparência no jogo nem a aceitação pelo VAC.
