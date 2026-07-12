# Especificação — Organização de meios por domínio e grupo de capacidade

> Documento portável para replicar, em **outro simulador que use o mesmo
> cenário** (Operação Atlântico Sul / Defesa da Bacia de Campos), a mesma
> organização de forças por **domínio** e **grupo de capacidade** adotada no
> `simulador-construtivo-CBP`. A referência doutrinária é a **Camada 2** da
> estrutura de classificação em três camadas dos artigos do autor — os
> **componentes de força de Coutau-Bégarie** (*Traité de stratégie navale*,
> item 350).
>
> Objetivo: garantir **uma única fonte da verdade** para a taxonomia, de modo
> que ordem de batalha, composição de pacotes de força, tabela de custos e
> **MOEs por componente** fiquem consistentes entre os dois simuladores.

---

## 1. As três camadas de classificação (resumo)

| Camada | Pergunta que responde | Uso no simulador |
|---|---|---|
| **1 — Função político-estratégica** (Booth/Grove) | *Para que serve o meio?* Militar (M) / Constabular (C), com alcance Local/Regional/Global | Anotação opcional por meio (não usada na mecânica de combate) |
| **2 — Componentes de força** (Coutau-Bégarie) | *Que papel o meio cumpre na força?* DISS, INTERV, VIG, COST, ANF, LOG (+ SEP) | **Camada operante desta especificação** — agrupa os meios |
| **3 — Categoria funcional de cômputo** (Cuervo Vázquez & Moloeznik) | *Como classificá-lo para contagem?* COMB, SUB, PAT, ANF, LOG, MCM… | Mapeável a partir da Camada 2 + domínio (ver §6) |

Esta especificação materializa a **Camada 2** como o eixo de agrupamento, por
ser a que melhor descreve **vocação de emprego** (o que interessa ao
planejamento baseado em capacidades), e a estende aos domínios não-navais
(aéreo, terrestre) e ao cibernético com grupos análogos.

---

## 2. Domínios

Cada grupo-tarefa pertence a exatamente **um domínio**. São cinco:

| Domínio | Código sugerido | Rótulo (com emoji) |
|---|---|---|
| Naval — Superfície | `NAV_SURF` | `⚓ Naval — Superfície` |
| Naval — Submarino | `NAV_SUB` | `🌊 Naval — Submarino` |
| Aéreo | `AIR` | `✈️ Aéreo` |
| Terrestre | `LAND` | `🏔️ Terrestre` |
| Cibernético | `CYBER` | `⚡ Cibernético` |

Além destes, um **pseudodomínio** para os ativos que **não são meios de
combate**, mas objetivos do cenário:

| Pseudodomínio | Código | Rótulo |
|---|---|---|
| Infraestrutura crítica | `INFRA` | `🏭 Infraestrutura crítica` |

FPSOs, portos e aeródromos entram aqui: são **objetivos a proteger/atacar**,
não itens de aquisição — ficam **fora do cômputo de força e de custo** dos
pacotes, mas **dentro das MOEs** (as perdas de infraestrutura são a medida de
eficácia central do cenário).

---

## 3. Grupos de capacidade (Camada 2 + análogos)

Siglas canônicas. As seis primeiras são os componentes de Coutau-Bégarie; as
demais são os grupos análogos para os domínios aéreo, terrestre e cibernético.

| Sigla | Componente / grupo | Domínio típico | Núcleo no cenário |
|---|---|---|---|
| `DISS` | Dissuasão (negação do mar) | Naval — Submarino | submarinos (SNAC, S-BR) |
| `INTERV` | Intervenção (zona de alto risco) | Naval — Superfície | grupo aeronaval / grupo de batalha |
| `VIG` | Vigilância (zona de menor risco) | Naval — Superfície | escoltas de superfície (fragatas) |
| `COST` | Costeira | Naval — Superfície | patrulha oceânica e costeira |
| `ANF` | Anfíbia | Naval — Superfície | navios de desembarque/multipropósito |
| `LOG` | Logística (trem de esquadra) | Naval — Superfície | petroleiros, apoio, munição |
| `DAE` | Defesa aérea / superioridade | Aéreo | caça |
| `PATMAR` | Patrulha marítima / ISR / AEW | Aéreo | patrulha marítima, alerta aéreo |
| `ATQ` | Ataque aeronaval | Aéreo | esquadrões de ataque |
| `DCOST` | Defesa costeira (A2/AD) | Terrestre | baterias de mísseis costeiros |
| `GBAD` | Defesa antiaérea | Terrestre | artilharia/mísseis antiaéreos |
| `OPESP` | Operações especiais | Terrestre | equipes de operações especiais |
| `CIB` | Guerra cibernética | Cibernético | estoques C2/SEN/WPN/LOG (não é grupo-tarefa) |
| `INFRA` | Ativos protegidos | Infraestrutura | FPSOs, portos, aeródromos |

> **Nota doutrinária (decisão de cenário).** No cenário Operação Atlântico Sul,
> tanto o **grupo aeronaval do NAM Atlântico (SAG-P, Azul)** quanto a **escolta
> do porta-aviões adversário (ESCCSG / RED-GE-1, Vermelho)** são computados em
> **INTERV** (intervenção), por serem os núcleos de combate de zona de alto
> risco. As demais escoltas de superfície ficam em **VIG**. Esta é uma escolha
> de classificação do cenário — replique-a no outro simulador para manter a
> comparabilidade.

---

## 4. Mapeamento canônico grupo-tarefa → (domínio, grupo)

Fonte da verdade, extraída do simulador. Use os **IDs** como chave; os nomes
entre parênteses são apenas mnemônicos.

### 4.1 Força Azul (Marinha do Brasil)

| Domínio | Grupo | Grupos-tarefa (ID · nome) |
|---|---|---|
| Naval — Superfície | `INTERV` | `BLUE-SAG-P` · SAG-P (NAM Atlântico + orgânicos) |
| Naval — Superfície | `VIG` | `BLUE-SAG-S1` · SAG-1 · `BLUE-SAG-S2` · SAG-2 |
| Naval — Superfície | `ANF` | `BLUE-ANFIB` · ANFIB |
| Naval — Superfície | `COST` | `BLUE-PAT-O1` · PAOC1 · `BLUE-PAT-O2` · PAOC2 · `BLUE-PAT-C1` · PATC1 · `BLUE-PAT-C2` · PATC2 |
| Naval — Superfície | `LOG` | `BLUE-LOG-A` · APLOG · `BLUE-LOG-T` · REAB |
| Naval — Submarino | `DISS` | `BLUE-SUB-N` · SBN · `BLUE-SUB-1` · SB1 · `BLUE-SUB-2` · SB2 · `BLUE-SUB-3` · SB3 |
| Aéreo | `DAE` | `BLUE-CACA-1` · PAC1 · `BLUE-CACA-2` · PAC2 |
| Aéreo | `PATMAR` | `BLUE-MPRA-1` · PATMAR1 · `BLUE-MPRA-2` · PATMAR2 |
| Aéreo | `ATQ` | `BLUE-CJAT-1` · APAER1 · `BLUE-CJAT-2` · APAER2 |
| Terrestre | `DCOST` | `BLUE-DCOST1` · DEFCOST1 · `BLUE-DCOST2` · DEFCOST2 |
| Terrestre | `GBAD` | `BLUE-ADA-1` · BDA1 · `BLUE-ADA-2` · BDA2 |
| Terrestre | `OPESP` | `BLUE-SEOP` · OpEsp Azul |
| Infraestrutura | `INFRA` | `BLUE-FPSO1..4` · FPSOs · `BLUE-PORTO-S/RJ/V/ACU` · portos · `BLUE-AERO-RJ/SP/CF` · aeródromos |

### 4.2 Força Vermelha (adversário)

| Domínio | Grupo | Grupos-tarefa (ID · nome) |
|---|---|---|
| Naval — Superfície | `INTERV` | `RED-GBPA` · CSG (porta-aviões) · `RED-GE-1` · ESCCSG (escolta do CSG) |
| Naval — Superfície | `VIG` | `RED-GE-2` · SAG1 · `RED-GE-3` · SAG2 |
| Naval — Superfície | `ANF` | `RED-GANF` · ANFIB-E |
| Naval — Superfície | `LOG` | `RED-AOR-G` · REAB · `RED-GLOG` · LOG1 · `RED-AKE` · LOG2 |
| Naval — Submarino | `DISS` | `RED-KSN` · SBN · `RED-KS-1` · SB |
| Aéreo | `DAE` | `RED-KMF-1` · PAC1 · `RED-KMF-2` · PAC2 |
| Aéreo | `PATMAR` | `RED-MPRA-K1` · PATMAR1 · `RED-MPRA-K2` · PATMAR2 · `RED-AWACS-K` · AWACS |
| Terrestre | `OPESP` | `RED-SEOP` · OpEsp Verm · `RED-SEOP-2` · OpEsp Verm 2 |

> O lado Vermelho não possui grupos `COST`, `ATQ`, `DCOST`, `GBAD` nem `INFRA`
> neste cenário. Grupos ausentes simplesmente **não geram entradas** — nunca
> assuma o conjunto completo de siglas por lado.

---

## 5. Estrutura de dados de referência

> **Arquivo pronto para carregar:** [`taxonomia_grupos_capacidade.json`](taxonomia_grupos_capacidade.json)
> — a taxonomia completa (gerada a partir do código, fiel por construção), com
> metadados de domínios, subtipos ciber, convenção de MOEs e as decisões de
> cenário. Prefira **importar esse arquivo** no outro simulador a copiar o bloco
> abaixo, que é apenas ilustrativo.

Uma única constante declarativa é suficiente; tudo o mais deriva dela. Formato
neutro (JSON/YAML/dict), reproduzível em qualquer linguagem:

```json
{
  "blue": [
    {"domain": "⚓ Naval — Superfície", "groups": [
      {"sigla": "INTERV", "label": "Intervenção (grupo aeronaval)", "units": ["BLUE-SAG-P"]},
      {"sigla": "VIG",    "label": "Vigilância (escolta oceânica)", "units": ["BLUE-SAG-S1", "BLUE-SAG-S2"]},
      {"sigla": "ANF",    "label": "Anfíbia",                       "units": ["BLUE-ANFIB"]},
      {"sigla": "COST",   "label": "Costeira (patrulha)",           "units": ["BLUE-PAT-O1", "BLUE-PAT-O2", "BLUE-PAT-C1", "BLUE-PAT-C2"]},
      {"sigla": "LOG",    "label": "Logística (trem de esquadra)",  "units": ["BLUE-LOG-A", "BLUE-LOG-T"]}
    ]},
    {"domain": "🌊 Naval — Submarino", "groups": [
      {"sigla": "DISS", "label": "Dissuasão (negação do mar)", "units": ["BLUE-SUB-N", "BLUE-SUB-1", "BLUE-SUB-2", "BLUE-SUB-3"]}
    ]},
    {"domain": "✈️ Aéreo", "groups": [
      {"sigla": "DAE",    "label": "Defesa aérea / superioridade", "units": ["BLUE-CACA-1", "BLUE-CACA-2"]},
      {"sigla": "PATMAR", "label": "Patrulha marítima e ISR",      "units": ["BLUE-MPRA-1", "BLUE-MPRA-2"]},
      {"sigla": "ATQ",    "label": "Ataque aeronaval",             "units": ["BLUE-CJAT-1", "BLUE-CJAT-2"]}
    ]},
    {"domain": "🏔️ Terrestre", "groups": [
      {"sigla": "DCOST", "label": "Defesa costeira (A2/AD)", "units": ["BLUE-DCOST1", "BLUE-DCOST2"]},
      {"sigla": "GBAD",  "label": "Defesa antiaérea",       "units": ["BLUE-ADA-1", "BLUE-ADA-2"]},
      {"sigla": "OPESP", "label": "Operações especiais",    "units": ["BLUE-SEOP"]}
    ]}
  ],
  "red": [
    {"domain": "⚓ Naval — Superfície", "groups": [
      {"sigla": "INTERV", "label": "Intervenção (grupo de batalha)", "units": ["RED-GBPA", "RED-GE-1"]},
      {"sigla": "VIG",    "label": "Vigilância (escoltas)",          "units": ["RED-GE-2", "RED-GE-3"]},
      {"sigla": "ANF",    "label": "Anfíbia",                        "units": ["RED-GANF"]},
      {"sigla": "LOG",    "label": "Logística",                      "units": ["RED-AOR-G", "RED-GLOG", "RED-AKE"]}
    ]},
    {"domain": "🌊 Naval — Submarino", "groups": [
      {"sigla": "DISS", "label": "Dissuasão (negação do mar)", "units": ["RED-KSN", "RED-KS-1"]}
    ]},
    {"domain": "✈️ Aéreo", "groups": [
      {"sigla": "DAE",    "label": "Caça embarcada",           "units": ["RED-KMF-1", "RED-KMF-2"]},
      {"sigla": "PATMAR", "label": "Patrulha marítima e AEW",  "units": ["RED-MPRA-K1", "RED-MPRA-K2", "RED-AWACS-K"]}
    ]},
    {"domain": "🏔️ Terrestre", "groups": [
      {"sigla": "OPESP", "label": "Operações especiais", "units": ["RED-SEOP", "RED-SEOP-2"]}
    ]}
  ]
}
```

O domínio cibernético **não** entra aqui: é modelado por **estoques** por
subtipo (`C2`, `SEN`, `WPN`, `LOG`), não por grupos-tarefa. Se o outro
simulador não tiver ciber, ignore.

### Funções derivadas (pseudocódigo)

```
classify_unit(unit_id, side):
    para cada dom em TAXONOMY[side]:
        para cada grp em dom.groups:
            se unit_id em grp.units:
                retorna (dom.domain, grp.sigla, grp.label)
    # fallback: ativo não listado → infraestrutura protegida
    retorna ("🏭 Infraestrutura crítica", "INFRA", "Ativo protegido")

taxonomy_order(side):        # p/ ordenar tabelas na ordem doutrinária
    retorna { unit_id: índice sequencial (domínio → grupo → posição) }

group_labels(side):          # [(sigla, label)] na ordem da taxonomia;
    ...                      # inclui ("INFRA", ...) ao final no lado azul
```

**Invariante a testar:** todo grupo-tarefa **de combate** (aquele que tem custo
de aquisição / entra em pacotes de força) deve estar na taxonomia; todo ativo
protegido deve cair no fallback `INFRA`. Verifique com uma asserção de
cobertura: `conjunto(unidades da taxonomia) == conjunto(unidades com custo)`.

---

## 6. Ponte para a Camada 3 (categoria funcional de cômputo)

Se o outro simulador precisar da **Camada 3** (COMB, SUB, PAT, ANF, LOG, MCM,
RES, TRA, RIV, AUX, HOSP, SEP), ela deriva de (domínio, grupo):

| (domínio, grupo) | Camada 3 |
|---|---|
| Naval-Superfície · INTERV/VIG | `COMB` (combatente de superfície) |
| Naval-Superfície · COST | `PAT` (patrulha) |
| Naval-Superfície · ANF | `ANF` |
| Naval-Superfície · LOG | `LOG` |
| Naval-Submarino · DISS | `SUB` |
| Aéreo · qualquer | (aviação naval — fora da taxonomia de cascos da Camada 3) |
| Terrestre / Cibernético | (fora do cômputo de cascos) |
| Infraestrutura · INFRA | `SEP` (fora do cômputo combatente) |

> A Camada 3 admite **campo primário e secundário** (dupla contagem para meios
> multipropósito); a Camada 2 aqui usa **atribuição única** por grupo-tarefa,
> por simplicidade da mecânica de simulação. Ao portar para a análise de frota
> dos artigos, reative a dupla contagem onde necessário.

---

## 7. MOEs agregadas por grupo de capacidade

O ganho analítico da taxonomia é agregar as **medidas de eficácia** por
componente, aproximando a saída do simulador da estrutura dos artigos. Padrão
adotado (replicável):

1. **Por partida**, para cada lado, calcule a **perda de poder de permanência
   (SP)** por grupo:

   ```
   perda%(grupo) = 100 · (1 − Σ SP_atual / Σ SP_inicial),  sobre as unidades do grupo
   ```

   Emita uma chave por grupo presente, no formato `grp_<lado>_<SIGLA>`
   (ex.: `grp_blue_DISS`, `grp_red_INTERV`). Ativos protegidos agregam em
   `grp_<lado>_INFRA`. Grupos ausentes da força **não** geram chave.

2. **Por lote (Monte Carlo)**, tire a **média das réplicas** de cada chave.

3. **Apresentação:** dois heatmaps *pacote × grupo* — (a) **perdas próprias**
   da força projetada e (b) **atrito imposto** aos componentes da ameaça — e/ou
   duas tabelas equivalentes no relatório, com “—” para grupos ausentes. A
   ordem das linhas segue `group_labels(side)`.

Essa decomposição revela padrões que a média agregada esconde — p.ex., a
vigilância (`VIG`) permanecer intacta enquanto dissuasão (`DISS`) e patrulha
marítima (`PATMAR`) absorvem o desgaste.

---

## 8. Checklist de replicação no outro simulador

- [ ] Reproduzir a constante da §5 como **fonte única da verdade**, com os
      **mesmos IDs** de grupo-tarefa do cenário (para comparabilidade entre os
      dois simuladores).
- [ ] Implementar `classify_unit` com o **fallback `INFRA`** para ativos
      protegidos.
- [ ] Manter a decisão de cenário: **SAG-P (Azul) e ESCCSG (Vermelho) em
      `INTERV`**.
- [ ] Ordenar ordem de batalha, composição de pacotes e tabela de custos pela
      `taxonomy_order`.
- [ ] Emitir as MOEs `grp_<lado>_<SIGLA>` por partida e agregá-las por lote.
- [ ] Teste de cobertura: unidades da taxonomia == unidades com custo; ativos
      protegidos caem em `INFRA`.
- [ ] Se os IDs de grupo-tarefa do outro simulador diferirem, manter uma
      **tabela de-para** para preservar a mesma taxonomia.

---

## 9. Referências

- **Coutau-Bégarie, H.** *Traité de stratégie navale* (item 350 — componentes
  da força naval): DISS, INTERV, VIG, COST, ANF, LOG, SEP.
- **Booth, K. / Grove, E.** Funções político-estratégicas do poder naval
  (Camada 1: Militar / Constabular; alcance Local/Regional/Global).
- **Cuervo Vázquez, Á. & Moloeznik, M. P.** Taxonomia funcional de cômputo
  (Camada 3, adaptada).
- Documento de trabalho do autor: *A evolução das capacidades navais
  brasileiras (1985–2025)* — estrutura de classificação em três camadas.

### Exemplo mínimo de carregamento (Python)

```python
import json

with open("taxonomia_grupos_capacidade.json", encoding="utf-8") as f:
    TAX = json.load(f)["taxonomia"]

def classify_unit(unit_id, side="blue"):
    for dom in TAX[side]:
        for grp in dom["groups"]:
            if unit_id in grp["units"]:
                return dom["domain"], grp["sigla"], grp["label"]
    return "🏭 Infraestrutura crítica", "INFRA", "Ativo protegido"
```

Em JS/Node: `const TAX = require("./taxonomia_grupos_capacidade.json").taxonomia;`
e a mesma varredura. O arquivo é UTF-8; preserve os emojis dos rótulos de
domínio (ou substitua-os por códigos como `NAV_SURF` se preferir rótulos ASCII).

---

*Consistente com `cbp_sim/cbp.py` (`FORCE_TAXONOMY`, `classify_unit`,
`taxonomy_order`, `group_labels`) e `cbp_sim/montecarlo.py`
(`group_loss_metrics`, `summarize_groups`) do `simulador-construtivo-CBP`.
O arquivo `taxonomia_grupos_capacidade.json` é gerado a partir de
`FORCE_TAXONOMY` — regenere-o se a taxonomia mudar.*
