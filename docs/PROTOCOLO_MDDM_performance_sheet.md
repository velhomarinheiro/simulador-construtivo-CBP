# Protocolo de coleta — *Performance Sheet* + MDDM
## Captura e descrição formal da tomada de decisão de jogadores humanos
### Cenário Operação Atlântico Sul — Defesa das bacias de Campos e Santos

> Instrumento de pesquisa para o wargame **Operação Atlântico Sul**, adaptado de
> Sakata, Kikuchi, Okumura, Kunigami, Yoshikawa, Yamamura e Terano (2020),
> *Uncovering Users' Decisions through Serious Game Playing with A Formal
> Description Method* (ITCA 2020), que combina a **Performance Sheet** (PS) de
> Koshiyama et al. com o **Managerial Decision-making Description Model**
> (MDDM) de Kunigami et al.
>
> É a terceira peça de um programa de três: o **log-cluster analysis** mapeia o
> espaço de cenários com bots, a **DEA** ordena por eficiência e aponta
> referências a imitar, e este protocolo captura **o que o jogador humano
> percebeu e por que mudou de ideia** — a camada cognitiva que nenhum log
> registra.

---

## 1. Objetivo e perguntas de pesquisa

**Objetivo.** Registrar, durante o jogo e sem interromper a partida, a
**cognição e o julgamento** do jogador — o estado que ele percebe, as variáveis
que observa, as que aciona e a **prioridade que atribui aos objetivos de
vitória** — e descrever formalmente esse percurso como um **diagrama de
decisão** MDDM, comparável entre jogadores, entre partidas e com os logs
gerados por bots.

**Perguntas.**

- **P1.** Ao longo de uma campanha, o jogador **muda a prioridade** entre as
  condições de vitória? Quando, e motivado por quê?
- **P2.** Que **eventos do ambiente** (detecção de um contato, perda de um
  grupo-tarefa, neutralização de uma FPSO, exaustão de combustível, anoitecer)
  antecedem essas mudanças?
- **P3.** O jogador observa e age sobre **quais camadas** da estrutura de força
  (estratégica, operacional, tática)? Seu escopo de observação é mais estreito
  que o conjunto efetivamente detectado pelos sensores?
- **P4.** As decisões humanas caem em **quais cenários** do espaço mapeado pelos
  bots (log-cluster), e como se posicionam na **fronteira de eficiência** (DEA)?

**Justificativa do desenho.** A alternativa clássica — *protocol analysis*
(pensar em voz alta, transcrever e codificar) — é inviável em exercício: exige
tempo de transcrição que não cabe entre o jogo e o debriefing. A PS resolve
isso registrando a cognição **no próprio turno**, em formulário curto, e foi
validada contra a *protocol analysis* por Koshiyama et al. com bons resultados.

---

## 2. O que cada fonte capta

O simulador **já registra automaticamente** a ação; a PS acrescenta a
**intenção**. Não duplicar o que o log fornece é o que mantém a ficha curta.

| Informação | Fonte | Observação |
|---|---|---|
| Movimentos, ataques declarados, alvos | Log JSONL (`movement_committed`, `attacks_declared`) | automático |
| Resultado de cada salva (T_atq, T_def, dano) | Log (`engagement_records`) | automático |
| Conjunto **detectado** por turno (névoa de guerra) | Motor (`detected_enemy_ids`) | automático — é o *escopo de observação disponível* |
| Progresso nas condições de vitória | Motor (`compute_objectives`) | automático |
| **Estado-alvo percebido** pelo jogador | **PS** | novo |
| **Variáveis que o jogador de fato observou** | **PS** | novo — subconjunto do disponível |
| **Prioridade atribuída aos objetivos** | **PS** | novo — base da "mudança de percepção" |
| **Motivo** declarado da mudança | **PS** + entrevista | novo |

> **Ponto metodológico.** A distinção entre o **detectado pelo sistema** e o
> **observado pelo jogador** é o que operacionaliza, no MDDM, o *escopo
> limitado (bounded scope) de observação do agente* — uma das quatro
> características do modelo. É uma vantagem deste cenário sobre o do artigo
> original: aqui o limite superior da observação é medido, não presumido.

---

## 3. As camadas do MDDM no cenário naval

O MDDM descreve a organização em camadas com símbolos de **objetivo** e
**meio**. A tradução para o cenário usa a mesma estrutura de classificação dos
artigos (Camada 2 — componentes de força de Coutau-Bégarie):

| Camada MDDM | Camada no cenário | Símbolos de **objetivo** | Símbolos de **meio** |
|---|---|---|---|
| Estratégica | Campanha | condições de vitória (ver §4.2) | pacote de força disponível |
| Intermediária | **Grupos de capacidade** | missão do componente (p. ex. "negar o mar", "proteger a infraestrutura") | DISS · INTERV · VIG · COST · ANF · LOG · DAE · PATMAR · ATQ · DCOST · GBAD · OPESP |
| Operativa (campo) | **Grupos-tarefa** | tarefa do grupo no turno | SAG-P, SAG-1, SBN, PATMAR1, DEFCOST1… |

O **elemento de decisão do agente** é o dispositivo de quatro terminais: os dois
superiores ligam-se ao que o jogador **observa**; os dois inferiores, àquilo
sobre o que ele **age**. O **componente de ambiente** (topo do diagrama)
recebe os estados e os **eventos** — que, neste cenário, saem em boa parte do
próprio log (detecção, perda de grupo, FPSO neutralizada, anoitecer, falta de
combustível).

---

## 4. Instrumentos

### 4.1 Performance Sheet — ficha por turno

Preenchida **ao final de cada turno**, antes da transição. Meta de tempo:
**60–90 segundos**. Um formulário por turno (ver ficha imprimível no Anexo A).

| # | Campo | Tipo | Instrução ao jogador |
|---|---|---|---|
| 1 | **Estado-alvo** | texto curto (≤ 15 palavras) | "Que situação você quer alcançar nos próximos turnos?" |
| 2 | **Variáveis observadas** | marcação múltipla | "O que você de fato olhou para decidir?" — SP próprio / SP inimigo / combustível (FP) / munição / contatos detectados / progresso dos objetivos / posição relativa / período (dia-noite) |
| 3 | **Leitura da situação** | texto curto | "Como você avalia a situação agora?" |
| 4 | **Variáveis de controle acionadas** | marcação múltipla + texto | "O que você decidiu?" — deslocar grupos / atacar / destacar escolta / reabastecer / recuar / manter posição — e **sobre qual grupo de capacidade** o esforço principal recaiu |
| 5 | **Prioridade dos objetivos** | ordenação (ver §4.2) | "Ordene as condições de vitória por prioridade **agora**." |
| 6 | **Objetivo próprio** (opcional) | texto | "Se nenhuma das condições traduz sua intenção, escreva a sua." |
| 7 | **Confiança** | 0–10 | "Quão confiante você está de que vencerá?" |
| 8 | **Mudou algo?** | sim/não + texto | Se a ordenação mudou em relação ao turno anterior: "por quê?" |

O campo 6 reproduz a permissão do artigo original de o jogador **acrescentar
objetivos próprios** quando os pré-registrados não descrevem sua intenção — e é
uma fonte valiosa: objetivos recorrentes escritos pelos jogadores indicam
lacuna nas condições de vitória do jogo.

### 4.2 Objetivos de vitória (os *play objectives*)

São as condições já formalizadas no jogo — não é preciso inventar objetivos.

**Força Azul — precisa de 3 de 5:**

| Código | Condição |
|---|---|
| `carrier` | Destruir o Porta-Aviões |
| `logistics` | Neutralizar ≥ 50% da Logística |
| `amphib` | Neutralizar o GT Anfíbio |
| `nucsub` | Destruir o Submarino Nuclear |
| `surface` | Degradar ≥ 50% dos Navios Combatentes |

**Força Vermelha — precisa das 2:**

| Código | Condição |
|---|---|
| `fpsos` | Neutralizar as 4 FPSOs |
| `ports` | Degradar ≥ 50% dos Portos |

> **Comparabilidade humano × bot.** O bot heurístico deriva suas prioridades das
> **mesmas** condições, e se re-tarefa ao cumpri-las (`botObjectiveWeights`).
> Humano e bot ficam, portanto, mensurados no mesmo instrumento — o que permite
> contrastar diretamente as duas sequências de prioridade.

### 4.3 Definição operacional de "mudança de percepção"

Seguindo o artigo, define-se **mudança de percepção** (*change in awareness*)
como **alteração na ordem de prioridade dos objetivos** entre dois turnos
consecutivos.

- **Detecção binária** (definição do artigo): a ordenação do turno *t* difere da
  do turno *t−1*.
- **Magnitude** (acréscimo recomendado): distância entre as duas ordenações por
  **τ de Kendall** ou número de inversões — distingue uma troca marginal de
  uma reordenação profunda.
- **Marcação**: na tabela de resultados, assinalar com `#` os turnos em que
  houve mudança, como na Tabela 5 do artigo.

Registrar também **mudança silenciosa**: ordenação estável, porém com alteração
do estado-alvo (campo 1) — indício de reinterpretação sem troca de prioridade.

### 4.4 Roteiro da entrevista de debriefing

Aplicada **logo após a partida** (ou, como no artigo, no dia seguinte;
preferir o mesmo dia para reduzir perda de memória). Semiestruturada, 15–20
min, gravada em áudio mediante consentimento. Apresentar ao jogador a **tabela
das suas próprias PS** e a linha do tempo dos eventos.

1. Descreva, em uma frase, o plano com que você entrou na partida.
2. *(Para cada turno marcado com `#`)* No turno **k** sua prioridade mudou de
   *X* para *Y*. **O que aconteceu** que o levou a isso?
3. Havia informação que você **gostaria de ter tido** e não tinha?
4. Houve momento em que percebeu que o plano inicial não se sustentava? Qual, e
   por qual sinal?
5. Que grupo de capacidade você considera ter sido **decisivo** — e qual foi
   **subutilizado**?
6. Se jogasse de novo, o que faria diferente no turno **k**?

As respostas de (2) alimentam os **símbolos de evento** do diagrama MDDM —
exatamente o uso que o artigo faz da entrevista.

---

## 5. Procedimento experimental

| Fase | Duração | Conteúdo |
|---|---|---|
| **Briefing** | 20 min | Cenário, ordem de batalha, condições de vitória, mecânica (turnos dia/noite, névoa, logística), **treino de preenchimento da PS** com 1 turno de exemplo |
| **Consentimento** | 5 min | Termo (§8), esclarecimento sobre gravação e anonimização |
| **Gaming** | 60–90 min | Partida; PS ao final de cada turno |
| **Debriefing** | 15–20 min | Entrevista (§4.4) com a tabela das PS à vista |
| **Total** | ~2h | |

**Participantes.** Instrutores e alunos da EGN. Amostra-alvo: **12–20**
jogadores, com **piloto de 2–3** para calibrar o tempo de preenchimento e a
clareza dos campos. Equilibrar os lados (Azul/Vermelho) e registrar
experiência prévia (jogos de guerra, tempo de serviço, especialidade) como
variáveis de controle.

**Modo de jogo.** Preferir **humano × bot** no piloto (isola a variável e
garante um adversário estável); humano × humano na fase principal, se o
efetivo permitir. Registrar o modo — ele condiciona a comparabilidade.

**Boas práticas.**

- Não interromper para "pensar em voz alta": a PS substitui a *protocol
  analysis* justamente para não perturbar o jogo.
- O facilitador **não** comenta decisões durante a partida.
- Numerar as fichas por `sessão · jogador · turno` antes de começar.
- Guardar o arquivo JSONL da partida com o **mesmo identificador** das fichas.

---

## 6. Esquema de dados (digitalização)

Digitalizar as fichas em CSV com uma linha por **turno-jogador**, para juntar ao
log automático pelo par (`sessao`, `turno`).

**`ps_<sessao>_<jogador>.csv`**

| Coluna | Tipo | Descrição |
|---|---|---|
| `sessao` | texto | identificador da partida (o mesmo do JSONL) |
| `jogador` | texto | código anonimizado (ex.: `P07`) |
| `lado` | `blue`/`red` | força comandada |
| `turno` | inteiro | número do turno |
| `periodo` | `dia`/`noite` | período |
| `estado_alvo` | texto | campo 1 |
| `obs_vars` | lista `;` | campo 2 (códigos: `sp_proprio`, `sp_inimigo`, `fp`, `municao`, `contatos`, `objetivos`, `posicao`, `periodo`) |
| `leitura` | texto | campo 3 |
| `ctrl_vars` | lista `;` | campo 4 (códigos: `deslocar`, `atacar`, `escoltar`, `reabastecer`, `recuar`, `manter`) |
| `grupo_esforco` | sigla | grupo de capacidade do esforço principal (DISS, INTERV, VIG, …) |
| `prioridade` | lista `>` | ordenação dos objetivos, ex.: `fpsos>ports` ou `carrier>logistics>surface>amphib>nucsub` |
| `objetivo_proprio` | texto | campo 6 (vazio se não houver) |
| `confianca` | 0–10 | campo 7 |
| `mudou` | 0/1 | campo 8 — derivável, mas registrar o auto-relato |
| `motivo` | texto | campo 8 |

**Junção com o log.** `sessao` + `turno` liga a PS a: conjunto detectado,
ataques declarados, resultados de salva e progresso dos objetivos. Disso saem
duas medidas derivadas:

- **cobertura de observação** = `|obs_vars declaradas|` frente ao que estava
  disponível (proxy do escopo limitado do agente);
- **aderência intenção-ação** = o `grupo_esforco` declarado coincide com o
  grupo efetivamente mais atacado no log daquele turno? A divergência é achado,
  não erro: indica intenção não realizada (por alcance, combustível ou
  detecção).

---

## 7. Construção do diagrama de decisão MDDM

Para cada partida, transcrever **um diagrama por jogador**. Passo a passo:

1. **Eixo do tempo** — horizontal, um marco por turno.
2. **Componente de ambiente** (faixa superior) — inserir os *símbolos de estado*
   (progresso dos objetivos, SP agregado por lado) e os *símbolos de evento*
   extraídos do log e da entrevista: `detecção do CSG`, `perda de SAG-2`,
   `FPSO-1 neutralizada`, `anoitecer`, `FP crítico`.
3. **Componente de estrutura de força** (faixas lateral esquerda/direita) — as
   três camadas de §3, com os símbolos de **objetivo** (condição de vitória
   priorizada no turno, campo 5 da PS) e de **meio** (grupo de capacidade
   acionado, campo 4).
4. **Elemento de decisão** (entre as faixas) — para cada turno com decisão
   relevante, o dispositivo de quatro terminais: acima, o que o jogador
   declarou observar (campo 2) — **não** o que estava disponível; abaixo, o que
   acionou (campo 4).
5. **Encadeamento** — ligar os elementos de decisão na ordem cronológica;
   marcar com seta de causalidade os pares *evento → mudança de prioridade*
   identificados em §4.3 e confirmados na entrevista.
6. **Destaque das mudanças** — assinalar os turnos `#` (mudança de percepção),
   que são os pontos de leitura do diagrama.

**Convenção mínima de símbolos** (suficiente para desenho manual ou em
ferramenta de diagramação):

| Elemento | Forma | Conteúdo |
|---|---|---|
| Estado | retângulo de canto reto | variável + valor |
| Evento | losango | descrição curta + turno |
| Objetivo | retângulo arredondado | código da condição de vitória |
| Meio | retângulo tracejado | sigla do grupo de capacidade |
| Decisão do agente | caixa com 4 terminais | 2 superiores: observado · 2 inferiores: acionado |

> **Custo realista.** A transcrição é **manual** e é a etapa mais cara do
> protocolo (estimativa: 30–60 min por partida). Recomenda-se transcrever
> integralmente **apenas as partidas selecionadas** — tipicamente uma por
> cenário identificado no log-cluster, mais os casos extremos da DEA.

---

## 8. Plano de análise (integração com os outros dois métodos)

1. **Descritiva** — tabela por jogador no formato da Tabela 5 do artigo:
   decisões e prioridade dos objetivos por turno, com `#` nas mudanças.
2. **Mudança de percepção** — frequência, turno modal e eventos antecedentes
   (P1, P2). Testar associação evento → mudança com tabela de contingência.
3. **Localização no espaço de cenários** — codificar a partida humana com o
   **mesmo alfabeto** do `logcluster` (grupo de capacidade por turno) e
   atribuí-la ao cenário mais próximo por distância de Levenshtein. Responde:
   *"o humano jogou como qual família de bots?"* (P4).
4. **Posição na fronteira** — inserir a partida humana como DMU na **DEA**, com
   os mesmos insumos e produtos; o *reference set* indica **qual log superior
   usar como referência no debriefing** — o uso prescritivo proposto por
   Sakata et al. (2021).
5. **Escopo de observação** — comparar `obs_vars` com o conjunto detectado
   (P3); testar se escopo mais estreito se associa a pior desempenho.
6. **Formalização** — diagramas MDDM das partidas selecionadas, comparados
   entre si e com um diagrama equivalente gerado de um log de bot.

---

## 9. Limitações e ressalvas

- **Base empírica do método é fina.** O artigo de referência valida a descrição
  com **um único participante**; trata-se de estudo exploratório. Este
  protocolo herda essa condição — os resultados iniciais devem ser tratados
  como **geração de hipóteses**, não como teste.
- **Reatividade do instrumento.** Preencher a PS pode, ele próprio, induzir o
  jogador a refletir e a mudar de prioridade. Mitigar mantendo a ficha curta e
  registrando, no piloto, o tempo médio de preenchimento; se possível, comparar
  um grupo sem PS (só log) para estimar o efeito.
- **Auto-relato.** Os campos 2 e 8 dependem de introspecção, sujeita a
  racionalização *a posteriori*. A entrevista atenua, mas não elimina.
- **Transcrição manual do MDDM** — custosa e com juízo do analista; recomenda-se
  **dupla codificação** de ao menos 20% das partidas e cálculo de concordância
  entre codificadores.
- **Poucos dados humanos disponíveis hoje.** O wargame tem apenas 16 partidas
  registradas, a maioria interrompida — a coleta precisa ser planejada, não
  aproveitada de histórico.
- **Ética.** Consentimento informado por escrito; anonimização por código;
  ausência de qualquer efeito avaliativo sobre o aluno (deixar explícito que o
  desempenho no jogo **não** compõe nota); direito de retirar-se a qualquer
  momento; guarda dos dados conforme a política da instituição e a LGPD.

---

## Anexo A — Ficha imprimível (um formulário por turno)

```
PERFORMANCE SHEET — Operação Atlântico Sul
Sessão: ______   Jogador: ______   Lado: ( ) Azul ( ) Vermelha
Turno: ____      Período: ( ) Dia ( ) Noite

1. ESTADO-ALVO (o que quero alcançar):
   _______________________________________________________________

2. O QUE OBSERVEI (marque):
   ( ) SP próprio      ( ) SP inimigo    ( ) Combustível (FP)
   ( ) Munição         ( ) Contatos      ( ) Progresso dos objetivos
   ( ) Posição relativa                  ( ) Período (dia/noite)

3. LEITURA DA SITUAÇÃO:
   _______________________________________________________________

4. O QUE DECIDI (marque e detalhe):
   ( ) Deslocar  ( ) Atacar  ( ) Destacar escolta
   ( ) Reabastecer  ( ) Recuar  ( ) Manter posição
   Esforço principal sobre o grupo: ______________________________
   (DISS · INTERV · VIG · COST · ANF · LOG · DAE · PATMAR · ATQ ·
    DCOST · GBAD · OPESP)

5. PRIORIDADE DOS OBJETIVOS (1 = maior):
   AZUL                              VERMELHA
   ___ Destruir Porta-Aviões         ___ Neutralizar as 4 FPSOs
   ___ Neutralizar ≥50% Logística    ___ Degradar ≥50% Portos
   ___ Neutralizar GT Anfíbio
   ___ Destruir Submarino Nuclear
   ___ Degradar ≥50% Combatentes

6. OBJETIVO PRÓPRIO (se nenhum acima traduz minha intenção):
   _______________________________________________________________

7. CONFIANÇA NA VITÓRIA:  0 1 2 3 4 5 6 7 8 9 10

8. MUDOU ALGO desde o turno anterior?  ( ) Não  ( ) Sim →
   Por quê? ______________________________________________________
```

## Anexo B — Tabela-síntese por jogador (modelo)

Formato da Tabela 5 do artigo; `#` marca alteração em relação ao turno anterior.

| Turno | Esforço | Controles acionados | Prio 1 | Prio 2 | Prio 3 | Conf. |
|---|---|---|---|---|---|---|
| 1 | DISS | deslocar | carrier | logistics | surface | 6 |
| 2 | DISS | deslocar; atacar | carrier | logistics | surface | 7 |
| 3 | VIG # | atacar; escoltar # | logistics # | carrier # | surface | 5 |
| … | | | | | | |

---

### Referências

- Sakata, A.; Kikuchi, T.; Okumura, R.; Kunigami, M.; Yoshikawa, A.; Yamamura,
  M.; Terano, T. (2020). *Uncovering Users' Decisions through Serious Game
  Playing with A Formal Description Method*. ITCA 2020.
- Sakata, A. et al. (2023). *Extracting Branch Factors of Scenarios from a
  Gaming Simulation Using Log-Cluster Analysis*. JACIII 27(2), 223–231.
- Sakata, A. et al. (2021). *Methodology for Extracting Knowledge from a Gaming
  Simulation Using Data Envelopment Analysis*. IJAS 14(1&2), 107–119.
- Kunigami, M. et al. — *Managerial Decision-making Description Model* (MDDM).
- Koshiyama, A. et al. — *Performance Sheet* em simulação e jogos.
- Coutau-Bégarie, H. *Traité de stratégie navale*, item 350 (componentes de
  força — Camada 2 da taxonomia do projeto).

*Documento de protocolo do `simulador-construtivo-CBP`; aplica-se ao wargame
**Operação Atlântico Sul**. Ver também `ESPEC_grupos_de_capacidade.md`
(taxonomia) e o módulo `cbp_sim/logcluster.py` (alfabeto de codificação usado
no item 3 do plano de análise).*
