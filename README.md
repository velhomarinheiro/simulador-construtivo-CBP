# Simulador Construtivo · Planejamento Baseado em Capacidades (CBP)

App **Streamlit** de simulação construtiva para análises de planejamento de
força no contexto do **Planejamento Baseado em Capacidades**, ambientado no
cenário do wargame **Operação Atlântico Sul**: defesa das infraestruturas
críticas nas bacias de Campos e Santos (FPSOs do pré-sal) e dos portos da
região Sudeste (Santos, Rio de Janeiro, Vitória e Açu), com a Força Azul
(Marinha do Brasil) opondo-se a uma força expedicionária adversária.

## Rodar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

Deploy no Streamlit Community Cloud: main file `app.py`, dependências em
`requirements.txt` (o pacote local `cbp_sim/` fica na raiz do repositório).

## Testes

```bash
pip install pytest
python -m pytest tests/ -q
```

## Metodologia

| Componente | Referência |
|---|---|
| Mecânica de jogo (mapa hex 16×10, turnos dia/noite, movimentação simultânea, rodadas de batalha com contra-ataque em grupo, logística, objetivos assimétricos) | wargame **Operação Atlântico Sul** (repos `wargame-naval` / `simulacao-construtiva-OAS`) |
| Adjudicação de engajamentos | **Equação de salva multidomínio** (repo `naval_salvo`): `ΔSP = (1/s)·𝟙⁽ᵈ'ᵈ⁾·[T_atq − T_def]₊`, com matriz de admissibilidade 5×5 (S/U/A/C/X) e nível marginal χ calibrável; letalidade e interceptação calibradas nas tabelas d6 do jogo original (modos estocástico e determinístico) |
| Domínio cibernético (X) | Modulador **Φ** do `naval_salvo` (eq. 12): `Φ(R)=1/[1+(R/r₀)^k]` sobre a razão de força ciber do oponente, por canal — ofensiva (C2/WPN), interceptação (SEN/WPN), detecção (SEN/C2) e logística (LOG); estoques por subtipo com contra-ciber próprio |
| Névoa de guerra (opcional) | Detecção por alcances por categoria (noite −1 hex; infraestrutura fixa sempre conhecida; Φ ciber degrada sensores); ataques exigem alvo detectado e, sem contato, o Azul assume estações defensivas junto às FPSOs/portos |
| Bot heurístico | Porte da IA do modo solo do wargame (doutrina orientada a objetivos, proteção de logística, gerência de combustível) + doutrina configurável de **escolta cerrada** de ativos críticos (defesa em grupo por empilhamento) |
| Bot de aprendizado de máquina | Pipeline em duas etapas: **clonagem comportamental** inspirada em `ml/train_bot.py` (estado 9×10×16 → redes de pontuação dos 160 hexes, em numpy puro) seguida de **aprendizado por reforço** (REINFORCE em auto-jogo contra o heurístico, recompensa orientada à missão, baseline de lote e bônus de entropia) |

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `app.py` | Roteador de navegação (`st.navigation`) — rótulos das páginas |
| `home.py` + `pages/` | Interface Streamlit (Página Inicial, Cenário, Simulação, Monte Carlo, Análise CBP, Bots, Relatórios) |
| `cbp_sim/engine.py` | Motor do jogo (estado, turnos, combate, objetivos, vitória, detecção) |
| `cbp_sim/salvo.py` | Equação de salva multidomínio e matriz de admissibilidade |
| `cbp_sim/cyber.py` | Domínio cibernético — modulador Φ por canal |
| `cbp_sim/hexmap.py` | Grade hexagonal odd-q e terrenos do teatro |
| `cbp_sim/oob_io.py` | Serialização da ordem de batalha em CSV (round-trip com JSON) |
| `cbp_sim/bots/` | Bot heurístico, bot ML (clonagem comportamental) e treinador RL (REINFORCE) |
| `cbp_sim/montecarlo.py` | Lotes de replicações e MOEs |
| `cbp_sim/cbp.py` | Pacotes de força, custos ilustrativos e perfis de capacidade |
| `cbp_sim/reporting.py` | Relatórios em Markdown |
| `cbp_sim/data/` | Ordem de batalha e tabelas de combate (exportadas do wargame) |
| `tests/` | Testes do núcleo (salva, motor, bots, CBP) |

## Fluxo de análise

1. **Cenário** — explore/edite a ordem de batalha, com upload/download em
   **JSON ou CSV** (o CSV traz uma linha por grupo-tarefa, editável em
   Excel/LibreOffice).
2. **Simulação** — uma partida bot × bot, turno a turno, com a decomposição
   T_atq/T_def de cada salva.
3. **Monte Carlo** — replicações com sementes controladas; distribuição das
   MOEs (P(vitória), sobrevivência das FPSOs, integridade portuária, perdas,
   razão de troca, duração).
4. **Análise CBP** — pacotes de força alternativos (presets + personalizados,
   incluindo opções cibernéticas e A2/AD) avaliados contra **pacotes de
   ameaça** (variantes da Força Vermelha); eficácia composta ponderada,
   custo-efetividade com **tabela de custos calibrável** (editor +
   upload/download) e perfil radar de capacidades; relatório comparativo
   para download. Os meios são organizados por **domínio** (naval-superfície,
   naval-submarino, aéreo, terrestre, cibernético) e por **grupos de
   capacidades** — para os meios navais, seguindo os componentes de força de
   Coutau-Bégarie (DISS/INTERV/VIG/COST/ANF/LOG, Camada 2 da estrutura de
   classificação em três camadas do Artigo 1) —, com a composição de cada
   pacote predefinido exibida em matriz-resumo e em detalhe por pacote.
5. **Bots** — ajuste da doutrina heurística (incl. escolta cerrada);
   geração de dataset por self-play e treino por clonagem comportamental;
   refino por **aprendizado por reforço** (lado, temperatura, pesos da
   recompensa, warm start) com curva de aprendizado; avaliação ML ×
   heurístico.
6. **Relatórios e Dados** — exportação (Markdown/CSV/JSON/JSONL) e importação
   de resultados, trilhas e modelos.

> **Aviso**: parâmetros, letalidades e custos são ilustrativos, destinados a
> comparação relativa entre alternativas de força. Calibre com fontes
> doutrinárias e orçamentárias antes de uso em estudos reais.
