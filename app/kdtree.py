"""KD-tree em 3D para busca dos k vizinhos mais próximos (k-NN).

Os pontos são as unidades de saúde convertidas para vetores na esfera
unitária (ver geo.para_vetor). Construção: O(n log n). Consulta k-NN:
em média O(log n + k), contra O(n) de uma varredura linear.
"""
import heapq
import math


class _No:
    __slots__ = ("ponto", "item", "eixo", "esq", "dir")

    def __init__(self, ponto, item, eixo, esq, dir_):
        self.ponto = ponto
        self.item = item
        self.eixo = eixo
        self.esq = esq
        self.dir = dir_


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


class KDTree:
    def __init__(self, pontos_e_itens):
        """pontos_e_itens: lista de tuplas ((x, y, z), item)."""
        self.tamanho = len(pontos_e_itens)
        self.raiz = self._construir(list(pontos_e_itens), 0)

    def _construir(self, pares, profundidade):
        if not pares:
            return None
        eixo = profundidade % 3
        pares.sort(key=lambda p: p[0][eixo])
        meio = len(pares) // 2
        ponto, item = pares[meio]
        return _No(
            ponto,
            item,
            eixo,
            self._construir(pares[:meio], profundidade + 1),
            self._construir(pares[meio + 1:], profundidade + 1),
        )

    def k_vizinhos(self, alvo, k, filtro=None, distancia_max=math.inf):
        """Retorna até k pares (distancia_euclidiana, item), do mais próximo
        ao mais distante, considerando só itens aceitos pelo filtro."""
        if k <= 0 or self.raiz is None:
            return []
        limite2 = distancia_max ** 2
        # heap de máximo (distância negativa) com os k melhores até agora
        melhores = []
        contador = 0  # desempate para itens não comparáveis

        def pior_aceito():
            if len(melhores) < k:
                return limite2
            return -melhores[0][0]

        def visitar(no):
            nonlocal contador
            if no is None:
                return
            d2 = _dist2(alvo, no.ponto)
            if d2 <= pior_aceito() and (filtro is None or filtro(no.item)):
                contador += 1
                if len(melhores) < k:
                    heapq.heappush(melhores, (-d2, contador, no.item))
                else:
                    heapq.heapreplace(melhores, (-d2, contador, no.item))
            diferenca = alvo[no.eixo] - no.ponto[no.eixo]
            primeiro, segundo = (no.esq, no.dir) if diferenca < 0 else (no.dir, no.esq)
            visitar(primeiro)
            # Só desce no outro lado se o hiperplano estiver mais perto que o pior aceito
            if diferenca ** 2 <= pior_aceito():
                visitar(segundo)

        visitar(self.raiz)
        resultado = sorted(((math.sqrt(-d2), c, item) for d2, c, item in melhores),
                           key=lambda t: (t[0], t[1]))
        return [(d, item) for d, _, item in resultado]
