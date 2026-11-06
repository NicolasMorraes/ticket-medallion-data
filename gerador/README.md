# Gerador de dados de teste

Gera arquivos de vendas e eventos com **a mesma estrutura** dos arquivos da `main`, para testar o pipeline (Raw → Bronze → Silver → Gold) sem tocar nos dados de produção.

## Como rodar pelo GitHub

1. Aba **Actions** → **Gerar dados de teste** → **Run workflow**.
2. Escolha os parâmetros e clique em **Run workflow**.
3. Ao terminar, os arquivos ficam na branch `dados-teste`, com os mesmos nomes da `main`.

Para o pipeline ler os dados de teste, troque só a branch na URL:

```
https://raw.githubusercontent.com/<usuario>/ticket-medallion-data/main/vendas_2025-10.csv.gz         (produção)
https://raw.githubusercontent.com/<usuario>/ticket-medallion-data/dados-teste/vendas_2025-10.csv.gz  (teste)
```

O workflow **se recusa** a publicar na `main`.

## Como rodar no computador

```
python gerador/gerar_dados.py --semente 42 --modo normal --saida saida
```

Só usa a biblioteca padrão do Python 3.10 ou superior.

## Parâmetros

| Parâmetro | Padrão | Para quê |
|---|---|---|
| `--semente` | 42 | mesma semente = arquivos idênticos; outra semente = dados novos com as mesmas regras |
| `--modo` | normal | `normal`: problemas do README · `estresse`: problemas novos (abaixo) |
| `--inicio` / `--fim` | 2025-10 / 2026-10 | período; um mês a mais testa listas de meses fixas no código |
| `--dias-ultimo-mes` | 7 | o último mês sai parcial, como o `2026-10` original; 0 = completo |
| `--pedidos-por-dia` | 1850 | volume (~80 mil linhas por mês) |
| `--clientes` | 40000 | tamanho da base de clientes |
| `--corte-esquema` | 2026-06 | mês em que `valor_total` vira `valor_total_brl` e entra `id_promotor` |
| `--meses-iso` | 2026-01,2026-02 | meses gravados em ISO-8859-1 (sem BOM) |

## O que o modo normal reproduz

| Problema do README | Como aparece |
|---|---|
| Datas em 4 formatos | ISO com `-03:00`, `dd/MM/yyyy HH:mm:ss` (horário local, sem fuso), ISO com `Z` (UTC) e epoch em milissegundos |
| Valores `"R$ 1.234,50"` | vírgula decimal, sem zeros à direita, às vezes com `R$` e ponto de milhar |
| CPF formatado, nulo ou inválido | com e sem pontuação, 10 dígitos (zero à esquerda perdido), `NULL`/`null`/vazio |
| E-mails sujos | espaços, maiúsculas, `n/a`, `sem-email`, `teste@` |
| Cidades e UFs inconsistentes | sem acento, maiúsculas, espaço no fim, `S. Paulo`, `Sampa`, `SAO PAULO - SP`, UF minúscula |
| Canal e status com caixa mista | `app`, `Aprovado`, e nulos em texto no canal |
| Nulos como vazio, `NULL`, `null` | no cupom, CPF, canal e artista do evento |
| Pedidos duplicados | cópias exatas e cópias que só diferem na forma de escrever |
| Pedidos que chegam atrasados | ~1% dos pedidos caem no arquivo do mês seguinte |
| Mudança para CANCELADO/ESTORNADO | ~3% dos aprovados ganham uma segunda versão, de 0 a 20 dias depois, às vezes no arquivo seguinte |
| Eventos órfãos | ~0,5% dos itens com `id_evento` de `EV-9000` em diante, que não existem no catálogo |
| Quantidade ≤ 0 | ~0,23% dos itens com 0, -1 ou -2 |
| Valores do pedido repetidos nos itens | subtotal, desconto, taxa e total repetidos em cada item |
| Eventos adiados (SCD2) | 8 eventos mudam de data no catálogo, com status `ADIADO` |

Regras de negócio mantidas: taxa de 15% (app e site), 10% (PDV) e 0 (bilheteria); cupons de 5%, 10% e 20%; meia pela metade do preço; parcelas só no cartão de crédito; `valor_total = subtotal - desconto + taxa`.

## O que o modo estresse acrescenta

São problemas que **não existem** nos arquivos originais. Cada um testa um ponto frágil do pipeline:

| Problema novo | O que testa |
|---|---|
| quinto formato de data: `yyyy-MM-dd HH:mm:ss` | o `F.when` das datas sem `otherwise` (vira nulo calado) |
| nulos escritos como `NA`, `-`, `N/D` | as listas fixas de textos de nulo |
| cidades `S.Paulo`, `Rio`, `BH` | o padrão de cidades escrito à mão |
| status com espaço no fim (`Cancelado `) | filtros por status exato |
| números com ponto decimal (`347.20`) | a troca de vírgula por ponto nos valores |
| um mês UTF-8 gravado em ISO-8859-1 (o do meio do período) | as listas fixas de encoding da Bronze |
| um mês com as colunas `canal` e `id_cliente` trocadas de lugar no cabeçalho | leitura de vários arquivos de uma vez com um cabeçalho só |
| data de evento no formato `yyyy/MM/dd` no catálogo | a conversão de datas dos eventos |

## Observações

- A geração é **determinística**: o mesmo commit do gerador, com a mesma semente e os mesmos parâmetros, produz arquivos idênticos byte a byte.
- Os dados são parecidos com os originais nas proporções, mas **não são iguais** a eles: os números de referência da Silver (1.004.170 linhas, 9.385 atrasados...) vão mudar. O que deve continuar valendo são as **regras**: zero nulos novos nas datas, uma linha por `id_pedido` + `item_seq`, percentuais somando 100.
- O modo estresse também muda os dados de base (consome números aleatórios diferentes), então compare um modo com o outro pelas regras, não pelos totais.
