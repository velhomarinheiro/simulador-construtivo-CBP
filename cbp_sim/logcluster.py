"""
Log-cluster analysis — extração de cenários e fatores de bifurcação.

Porte do método de Sakata et al. (2023), *Extracting Branch Factors of
Scenarios from a Gaming Simulation Using Log-Cluster Analysis*, JACIII
27(2), aplicado às trilhas JSONL do simulador construtivo:

1. **Codificação** — a história de decisões de cada partida vira um
   **código-string**, um símbolo por turno. O alfabeto usado é o dos
   **grupos de capacidade** (Camada 2), de modo que a análise fala a
   mesma língua da taxonomia dos artigos: cada símbolo diz *contra que
   componente da força adversária o esforço foi dirigido naquele turno*.
2. **Distância** — distância de **Levenshtein** entre códigos.
3. **Agrupamento** — clusterização hierárquica sobre a matriz de
   distâncias; cada grupo é um **cenário**.
4. **Fatores de bifurcação** — os códigos viram vetores binários
   ``turno × símbolo``; uma **árvore de decisão** (critério de entropia)
   treinada com o cenário como rótulo revela *quando e qual decisão*
   separa os cenários, com validação cruzada.
5. **Teste de hipótese** — Mann-Whitney U compara uma MOE entre dois
   cenários, como no artigo original.

Nota metodológica: o artigo aplica o método de Ward sobre distâncias de
Levenshtein. Ward pressupõe distâncias euclidianas, de modo que essa
combinação é uma prática comum porém frouxa; por isso ``cluster_codes``
aceita também ``average``/``complete``, válidos para matrizes de
distância arbitrárias. O padrão reproduz o artigo (``ward``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import mannwhitneyu

from .cbp import classify_unit

#: Sigla do grupo de capacidade → símbolo de um caractere (único).
SYMBOLS: dict[str, str] = {
    "DISS": "D",     # dissuasão (submarinos)
    "INTERV": "I",   # intervenção (grupo de batalha / aeronaval)
    "VIG": "V",      # vigilância (escoltas)
    "COST": "C",     # costeira (patrulha)
    "ANF": "A",      # anfíbia
    "LOG": "L",      # logística
    "DAE": "F",      # defesa aérea / caça
    "PATMAR": "P",   # patrulha marítima / ISR / AEW
    "ATQ": "Q",      # ataque aeronaval
    "DCOST": "K",    # defesa costeira
    "GBAD": "G",     # defesa antiaérea
    "OPESP": "E",    # operações especiais
    "INFRA": "N",    # infraestrutura (ativo protegido)
}
NO_ACTION = "-"      #: turno sem ataque declarado
CAMPAIGN_END = "."   #: preenchimento após o fim da campanha (horizonte comum)

SYMBOL_LABELS = ({v: k for k, v in SYMBOLS.items()}
                 | {NO_ACTION: "sem ataque",
                    CAMPAIGN_END: "campanha encerrada"})


# ── 1. Codificação das trilhas ───────────────────────────────────────────────

def suggest_horizon(codes: list[str], coverage: float = 0.8) -> int:
    """
    Horizonte comum sugerido: o maior *k* tal que ao menos ``coverage``
    das partidas ainda estavam em curso no turno *k*.

    As campanhas terminam em turnos diferentes; sem um horizonte comum, a
    distância de Levenshtein passa a ser dominada pela **diferença de
    comprimento** e o agrupamento captura apenas a duração — não a
    decisão. (No artigo original todas as partidas tinham 10 rodadas
    fixas, e o problema não se coloca.)
    """
    if not codes:
        return 0
    comprimentos = np.sort(np.array([len(c) for c in codes]))
    k = int(np.quantile(comprimentos, 1.0 - coverage, method="lower"))
    return max(1, k)


def encode_trail(trail: dict, side: str = "blue",
                 horizon: int | None = None) -> str:
    """
    Converte a trilha de uma partida no código-string das decisões.

    Um símbolo por fase de ataque do lado ``side``: o grupo de capacidade
    (Camada 2) mais visado naquele turno; ``-`` se nenhum ataque foi
    declarado. Com ``horizon``, o código é truncado nesse turno e as
    campanhas encerradas antes são completadas com ``.`` — todos os
    códigos passam a ter o mesmo comprimento, de modo que o agrupamento
    reflita a **escolha de alvo por turno**, e não a duração da campanha.
    """
    alvo_side = "red" if side == "blue" else "blue"
    seq: list[str] = []
    for ev in trail.get("events", []):
        if ev.get("event") != "attacks_declared" or ev.get("team") != side:
            continue
        alvos = [a.get("targetId") for a in (ev.get("attacks") or [])
                 if a.get("targetId")]
        if not alvos:
            seq.append(NO_ACTION)
            continue
        contagem: dict[str, int] = {}
        for uid in alvos:
            sig = classify_unit(uid, alvo_side)[1]
            contagem[sig] = contagem.get(sig, 0) + 1
        # desempate estável: mais frequente, depois ordem alfabética da sigla
        sig = min(contagem.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        seq.append(SYMBOLS.get(sig, "?"))
    code = "".join(seq)
    if horizon is not None and horizon > 0:
        code = code[:horizon].ljust(horizon, CAMPAIGN_END)
    return code


def encode_trails(trails: list[dict], side: str = "blue",
                  horizon: int | None = None) -> list[str]:
    """Códigos-string de um conjunto de trilhas."""
    return [encode_trail(t, side, horizon=horizon) for t in trails]


# ── 2. Distância de Levenshtein ──────────────────────────────────────────────

def levenshtein(a: str, b: str) -> int:
    """Distância de edição entre dois códigos (programação dinâmica)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1,          # deleção
                           cur[j - 1] + 1,       # inserção
                           prev[j - 1] + (ca != cb)))  # substituição
        prev = cur
    return prev[-1]


def distance_matrix(codes: list[str]) -> np.ndarray:
    """Matriz de distâncias condensada (formato aceito por ``linkage``)."""
    n = len(codes)
    out = np.zeros(n * (n - 1) // 2, dtype=float)
    k = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            out[k] = levenshtein(codes[i], codes[j])
            k += 1
    return out


# ── 3. Agrupamento hierárquico → cenários ────────────────────────────────────

def cluster_codes(codes: list[str], n_clusters: int = 2,
                  method: str = "ward"):
    """
    Agrupa os códigos em ``n_clusters`` cenários.

    Retorna ``(labels, Z, condensed)`` — rótulos 1..k, a matriz de ligação
    e a matriz de distâncias condensada (reaproveitável no dendrograma).
    """
    if len(codes) < 2:
        raise ValueError("é preciso ao menos duas partidas para agrupar")
    cond = distance_matrix(codes)
    Z = linkage(cond, method=method)
    k = max(1, min(int(n_clusters), len(codes)))
    labels = fcluster(Z, t=k, criterion="maxclust")
    return labels, Z, cond


def dendrogram_coords(Z: np.ndarray):
    """Coordenadas do dendrograma (icoord/dcoord) para desenho externo."""
    d = dendrogram(Z, no_plot=True)
    return d["icoord"], d["dcoord"], d["ivl"]


# ── 4. Vetores de características e árvore de decisão ────────────────────────

def featurize(codes: list[str]):
    """
    Códigos → matriz binária de características ``turno × símbolo``.

    A característica ``t{k}={S}`` vale 1 quando, no turno *k*, o esforço
    foi dirigido ao símbolo *S*. Códigos mais curtos (campanha encerrada
    antes) simplesmente têm zeros nos turnos posteriores. É esta
    codificação que produz fatores de bifurcação no formato do artigo:
    *"escolheu X na rodada k?"*.
    """
    max_len = max((len(c) for c in codes), default=0)
    simbolos = sorted({ch for c in codes for ch in c})
    nomes = [f"t{k + 1}={s}" for k in range(max_len) for s in simbolos]
    F = np.zeros((len(codes), len(nomes)), dtype=np.int8)
    idx = {(k, s): i for i, (k, s) in enumerate(
        (k, s) for k in range(max_len) for s in simbolos)}
    for r, code in enumerate(codes):
        for k, ch in enumerate(code):
            j = idx.get((k, ch))
            if j is not None:
                F[r, j] = 1
    return F, nomes


def _entropy(y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    _, cnt = np.unique(y, return_counts=True)
    p = cnt / cnt.sum()
    return float(-(p * np.log2(p)).sum())


@dataclass
class _Node:
    feature: int | None = None
    left: "_Node | None" = None      # ramo da característica = 0
    right: "_Node | None" = None     # ramo da característica = 1
    prediction: int | None = None
    n: int = 0
    gain: float = 0.0


class DecisionTree:
    """
    Árvore de decisão binária com critério de entropia (aproximação do
    C4.5 usada no artigo), escrita em numpy para manter o projeto sem
    dependências pesadas. Características são binárias, portanto cada
    corte é a pergunta *"esta decisão ocorreu?"*.
    """

    def __init__(self, max_depth: int = 3, min_samples_leaf: int = 1):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.root: _Node | None = None
        self.feature_names: list[str] = []

    def fit(self, F: np.ndarray, y: np.ndarray,
            feature_names: list[str] | None = None) -> "DecisionTree":
        self.feature_names = list(feature_names or
                                  [f"f{i}" for i in range(F.shape[1])])
        self.root = self._build(F, np.asarray(y), depth=0)
        return self

    def _build(self, F, y, depth) -> _Node:
        maioria = int(np.bincount(y).argmax()) if y.size else 0
        node = _Node(prediction=maioria, n=int(y.size))
        if (y.size == 0 or depth >= self.max_depth
                or np.unique(y).size == 1
                or y.size < 2 * self.min_samples_leaf):
            return node

        base, melhor, corte = _entropy(y), 0.0, None
        for j in range(F.shape[1]):
            mask = F[:, j] == 1
            n1, n0 = int(mask.sum()), int((~mask).sum())
            if n1 < self.min_samples_leaf or n0 < self.min_samples_leaf:
                continue
            ganho = base - (n0 * _entropy(y[~mask])
                            + n1 * _entropy(y[mask])) / y.size
            if ganho > melhor + 1e-12:
                melhor, corte = ganho, j
        if corte is None:
            return node

        mask = F[:, corte] == 1
        node.feature, node.gain = corte, melhor
        node.left = self._build(F[~mask], y[~mask], depth + 1)
        node.right = self._build(F[mask], y[mask], depth + 1)
        return node

    def predict(self, F: np.ndarray) -> np.ndarray:
        out = np.empty(F.shape[0], dtype=int)
        for i, row in enumerate(F):
            node = self.root
            while node is not None and node.feature is not None:
                node = node.right if row[node.feature] == 1 else node.left
            out[i] = node.prediction if node else 0
        return out

    def rules(self) -> list[dict]:
        """Caminhos raiz→folha como regras legíveis (os fatores de bifurcação)."""
        regras: list[dict] = []

        def walk(node: _Node, cond: list[str]):
            if node is None:
                return
            if node.feature is None:
                regras.append({"condicoes": list(cond),
                               "cenario": node.prediction, "n": node.n})
                return
            nome = self.feature_names[node.feature]
            walk(node.left, cond + [f"NÃO {nome}"])
            walk(node.right, cond + [nome])

        walk(self.root, [])
        return regras

    def root_factor(self) -> tuple[str, float] | None:
        """Característica do corte-raiz — o fator de bifurcação principal."""
        if self.root is None or self.root.feature is None:
            return None
        return self.feature_names[self.root.feature], self.root.gain


# ── 5. Validação cruzada e teste de hipótese ─────────────────────────────────

def cross_validate(F: np.ndarray, y: np.ndarray, feature_names: list[str],
                   k: int = 4, max_depth: int = 3, seed: int = 0) -> dict:
    """
    Validação cruzada k-fold da árvore, com precisão/revocação/F1 por
    cenário e acurácia global — as métricas reportadas no artigo.
    """
    y = np.asarray(y)
    n = y.size
    k = max(2, min(k, n))
    rng = np.random.default_rng(seed)
    ordem = rng.permutation(n)
    folds = np.array_split(ordem, k)

    classes = np.unique(y)
    tp = {c: 0 for c in classes}
    fp = {c: 0 for c in classes}
    fn = {c: 0 for c in classes}
    acertos = total = 0
    for f in folds:
        teste = np.zeros(n, dtype=bool)
        teste[f] = True
        if teste.all() or (~teste).sum() < 2:
            continue
        tree = DecisionTree(max_depth=max_depth).fit(
            F[~teste], y[~teste], feature_names)
        pred = tree.predict(F[teste])
        real = y[teste]
        acertos += int((pred == real).sum())
        total += real.size
        for c in classes:
            tp[c] += int(((pred == c) & (real == c)).sum())
            fp[c] += int(((pred == c) & (real != c)).sum())
            fn[c] += int(((pred != c) & (real == c)).sum())

    por_cenario = {}
    for c in classes:
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        por_cenario[int(c)] = {"precisao": prec, "revocacao": rec, "f1": f1,
                               "n": int((y == c).sum())}
    return {"acuracia": acertos / total if total else 0.0,
            "por_cenario": por_cenario, "k": k}


def compare_scenarios(values: np.ndarray, labels: np.ndarray,
                      a: int, b: int) -> dict:
    """
    Teste de Mann-Whitney U entre dois cenários para uma MOE — o mesmo
    teste que o artigo usa para contrastar cenários vizinhos.
    """
    va = np.asarray(values)[np.asarray(labels) == a]
    vb = np.asarray(values)[np.asarray(labels) == b]
    if va.size == 0 or vb.size == 0:
        return {"n_a": int(va.size), "n_b": int(vb.size), "p": float("nan"),
                "U": float("nan"), "mediana_a": float("nan"),
                "mediana_b": float("nan")}
    try:
        U, p = mannwhitneyu(va, vb, alternative="two-sided")
    except ValueError:                      # amostras idênticas / constantes
        U, p = float("nan"), 1.0
    return {"n_a": int(va.size), "n_b": int(vb.size), "U": float(U),
            "p": float(p), "mediana_a": float(np.median(va)),
            "mediana_b": float(np.median(vb))}


# ── 6. Pipeline completo ─────────────────────────────────────────────────────

@dataclass
class LogClusterResult:
    codes: list[str]
    labels: np.ndarray
    Z: np.ndarray
    features: np.ndarray
    feature_names: list[str]
    tree: DecisionTree
    cv: dict
    side: str
    horizon: int | None = None
    scenarios: dict[int, dict] = field(default_factory=dict)

    def scenario_table(self):
        """Resumo por cenário: nº de partidas, códigos mais frequentes."""
        import pandas as pd
        linhas = []
        for c in sorted(set(int(x) for x in self.labels)):
            membros = [self.codes[i] for i in range(len(self.codes))
                       if self.labels[i] == c]
            freq: dict[str, int] = {}
            for m in membros:
                freq[m] = freq.get(m, 0) + 1
            top = sorted(freq.items(), key=lambda kv: -kv[1])[:3]
            linhas.append({
                "Cenário": f"S{c}",
                "Partidas": len(membros),
                "Proporção": len(membros) / len(self.codes),
                "Códigos mais frequentes": " · ".join(
                    f"{c_}×{n}" for c_, n in top),
                "Comprimento médio": float(np.mean([len(m) for m in membros])),
            })
        return pd.DataFrame(linhas)


def run_log_cluster_analysis(trails: list[dict], *, side: str = "blue",
                             n_clusters: int = 2, method: str = "ward",
                             max_depth: int = 3, cv_folds: int = 4,
                             horizon: int | None = None,
                             seed: int = 0) -> LogClusterResult:
    """
    Executa o pipeline completo sobre as trilhas: codificação →
    Levenshtein → agrupamento → árvore de decisão → validação cruzada.

    ``horizon`` fixa um turno-limite comum (ver :func:`suggest_horizon`);
    sem ele, campanhas de durações diferentes fazem o agrupamento
    capturar sobretudo a duração.
    """
    codes = encode_trails(trails, side=side, horizon=horizon)
    if len(codes) < 2:
        raise ValueError("é preciso ao menos duas partidas para a análise")
    labels, Z, _ = cluster_codes(codes, n_clusters=n_clusters, method=method)
    F, nomes = featurize(codes)
    y = np.asarray(labels, dtype=int)
    tree = DecisionTree(max_depth=max_depth).fit(F, y, nomes)
    cv = cross_validate(F, y, nomes, k=cv_folds, max_depth=max_depth,
                        seed=seed)
    return LogClusterResult(codes=codes, labels=y, Z=Z, features=F,
                            feature_names=nomes, tree=tree, cv=cv, side=side,
                            horizon=horizon)


def trail_outcomes(trails: list[dict]):
    """
    MOEs por trilha, extraídas do evento ``game_over`` — deixa a análise
    auto-suficiente, inclusive para trilhas importadas de JSONL (sem
    depender do DataFrame do lote).
    """
    import pandas as pd
    linhas = []
    for t in trails:
        fim = next((e for e in reversed(t.get("events", []))
                    if e.get("event") == "game_over"), None)
        linha = {"run": t.get("run"), "winner": t.get("winner"),
                 "turns": np.nan, "fpsos_surviving": np.nan,
                 "port_integrity_pct": np.nan}
        if fim is not None:
            linha["winner"] = fim.get("winner", linha["winner"])
            linha["turns"] = fim.get("turn", np.nan)
            unidades = (fim.get("state") or {}).get("units") or []
            fpsos = [u for u in unidades if str(u.get("id", "")).startswith(
                "BLUE-FPSO")]
            portos = [u for u in unidades if str(u.get("id", "")).startswith(
                "BLUE-PORTO")]
            if fpsos:
                linha["fpsos_surviving"] = sum(1 for u in fpsos
                                               if (u.get("hp") or 0) > 0)
            tot = sum((u.get("maxHp") or 0) for u in portos)
            if tot:
                linha["port_integrity_pct"] = 100.0 * sum(
                    max(0.0, u.get("hp") or 0) for u in portos) / tot
        linhas.append(linha)
    return pd.DataFrame(linhas)


def describe_feature(nome: str) -> str:
    """``t5=I`` → ``turno 5: esforço sobre INTERV``."""
    if "=" not in nome:
        return nome
    turno, sim = nome.split("=", 1)
    rot = SYMBOL_LABELS.get(sim, sim)
    return f"turno {turno.lstrip('t')}: esforço sobre {rot}"
