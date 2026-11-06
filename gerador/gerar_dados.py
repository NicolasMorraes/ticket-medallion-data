"""
Gerador sintético de vendas de ingressos e catálogo de eventos.

Reproduz a estrutura dos arquivos do repositório ticket-medallion-data:
  - vendas_AAAA-MM.csv.gz : 1 linha por item de pedido, separador ';',
    decimal com vírgula, CRLF, gzip, UTF-8 com BOM (ISO-8859-1 nos meses
    configurados), troca de esquema a partir de um mês de corte.
  - eventos_AAAA-MM.csv   : snapshot do catálogo no dia 1 de cada mês.

Os problemas de qualidade do README são embutidos em proporções parecidas
com as dos arquivos originais. O modo "estresse" acrescenta problemas
NOVOS, que o pipeline atual não conhece, para testar a robustez.

A geração é determinística: mesma semente + mesmos parâmetros = mesmos arquivos.
Só usa a biblioteca padrão do Python.
"""

import argparse
import calendar
import csv
import gzip
import io
import os
import random
from datetime import date, datetime, timedelta, timezone

TZ_BR = timezone(timedelta(hours=-3))

# --------------------------------------------------------------------------
# Listas de apoio (fictícias)
# --------------------------------------------------------------------------
NOMES = ["Ana", "Beatriz", "Bruno", "Caio", "Carla", "Diego", "Eduarda", "Felipe",
         "Gabriela", "Henrique", "Isabela", "João", "Juliana", "Larissa", "Lucas",
         "Marcos", "Mariana", "Natália", "Otávio", "Paula", "Rafael", "Sofia",
         "Thiago", "Vanessa", "William"]
SOBRENOMES = ["Silva", "Souza", "Costa", "Lima", "Pereira", "Oliveira", "Santos",
              "Rodrigues", "Almeida", "Nascimento", "Carvalho", "Gomes", "Martins",
              "Araújo", "Ribeiro", "Rocha", "Dias", "Teixeira", "Barbosa", "Moreira"]
DOMINIOS = ["gmail.com", "hotmail.com", "uol.com.br", "outlook.com", "yahoo.com.br"]

CIDADES = [  # (cidade, uf, peso)
    ("São Paulo", "SP", 30.0), ("Rio de Janeiro", "RJ", 17.5), ("Belo Horizonte", "MG", 7.7),
    ("Porto Alegre", "RS", 5.8), ("Curitiba", "PR", 5.6), ("Brasília", "DF", 5.6),
    ("Recife", "PE", 4.9), ("Salvador", "BA", 4.8), ("Campinas", "SP", 3.9),
    ("Fortaleza", "CE", 3.7), ("Florianópolis", "SC", 2.9), ("Goiânia", "GO", 2.9),
    ("Manaus", "AM", 2.0), ("Belém", "PA", 1.9), ("Vitória", "ES", 1.8),
]
SEM_ACENTO = str.maketrans("ÁÂÃÉÊÍÓÔÕÚÇáâãéêíóôõúç", "AAAEEIOOOUCaaaeeiooouc")

LOCAIS = [  # (local, cidade, uf, tipo)
    ("Arena Horizonte", "São Paulo", "SP", "arena"), ("Pavilhão Aurora", "São Paulo", "SP", "arena"),
    ("Parque Expo Sul", "São Paulo", "SP", "parque"), ("Teatro Lumière", "São Paulo", "SP", "teatro"),
    ("Hall Campinas", "Campinas", "SP", "arena"), ("Casa Atlântica", "Rio de Janeiro", "RJ", "arena"),
    ("Estádio Maré Alta", "Rio de Janeiro", "RJ", "estadio"), ("Teatro do Cais", "Rio de Janeiro", "RJ", "teatro"),
    ("Arena Serra Verde", "Belo Horizonte", "MG", "arena"), ("Arena dos Pampas", "Porto Alegre", "RS", "arena"),
    ("Espaço Pinhal", "Curitiba", "PR", "arena"), ("Centro Cerrado", "Brasília", "DF", "arena"),
    ("Arena Recifes", "Recife", "PE", "arena"), ("Arena Farol", "Salvador", "BA", "arena"),
    ("Teatro Jangada", "Fortaleza", "CE", "teatro"), ("Espaço Ilha", "Florianópolis", "SC", "arena"),
    ("Arena Ipê", "Goiânia", "GO", "arena"),
]
ARTISTAS = ["Ana Vitral", "Banda Aurora Boreal", "Banda Farol Azul", "Coletivo Asfalto",
            "Coral Sinfônico Vértice", "DJ Neon Tropical", "Duo Cafezal", "João Ladeira",
            "Lina Prisma", "Lua de Cristal", "MC Horizonte", "Maré Cheia", "Orquestra Brisa",
            "Os Navegantes", "Os Sertanejos do Vale", "Pedra Solar", "Rock Cardeal",
            "Rádio Satélite", "Samba da Esquina", "Trio Ventania"]
TURNES = ["Luz", "Infinito", "Raízes", "Viagem", "Agora"]
PECAS = ["O Último Ato", "Musical Estrelas", "Comédia em Três Tempos", "O Mágico da Ilha",
         "Stand-up Noite Leve"]
FESTIVAIS = ["Festival Verão Sonoro", "Festival Noites de Ouro", "Festival Som da Cidade"]
TIMES = ["Falcões AC", "Gaviões do Sul", "Tubarões FC", "Leões do Norte"]

SETORES = {  # categoria -> [(setor, preco_base, peso)]
    "SHOW": [("PISTA", 150, 50), ("PISTA_PREMIUM", 300, 23), ("CADEIRA", 260, 13), ("CAMAROTE", 600, 8)],
    "FESTIVAL": [("PISTA", 180, 55), ("PISTA_PREMIUM", 340, 25), ("CAMAROTE", 650, 10)],
    "TEATRO": [("PLATEIA", 110, 60), ("PLATEIA_VIP", 190, 25), ("BALCAO", 70, 15)],
    "ESPORTE": [("ARQUIBANCADA", 90, 65), ("CADEIRA", 160, 25), ("CAMAROTE", 420, 10)],
}
CUPONS = {"PRIMEIRACOMPRA": 0.05, "APP5": 0.05, "FAN10": 0.10, "BLACK20": 0.20}
TAXA_CANAL = {"APP": 0.15, "SITE": 0.15, "PDV": 0.10, "BILHETERIA": 0.0}
CANAIS = [("APP", 47), ("SITE", 37), ("BILHETERIA", 9), ("PDV", 5)]
PAGAMENTO_CANAL = {
    "APP": [("CARTAO_CREDITO", 62), ("PIX", 30), ("CARTAO_DEBITO", 5), ("BOLETO", 3)],
    "SITE": [("CARTAO_CREDITO", 62), ("PIX", 30), ("CARTAO_DEBITO", 5), ("BOLETO", 3)],
    "BILHETERIA": [("CARTAO_DEBITO", 39), ("CARTAO_CREDITO", 31), ("DINHEIRO", 30)],
    "PDV": [("CARTAO_CREDITO", 64), ("PIX", 31), ("CARTAO_DEBITO", 5)],
}
PARCELAS_CREDITO = [(1, 50), (2, 15), (3, 15), (6, 12), (10, 8)]
# Fator de preço por mês (o ticket médio cresce até junho e acomoda depois)
FATOR_MES = {10: 1.00, 11: 1.00, 12: 1.03, 1: 1.01, 2: 0.94, 3: 1.03, 4: 1.13,
             5: 1.18, 6: 1.22, 7: 1.11, 8: 1.11, 9: 1.12}

COLUNAS_ANTIGO = ["id_pedido", "item_seq", "data_pedido", "data_atualizacao", "status", "canal",
                  "id_cliente", "nome_cliente", "cpf", "email", "data_nascimento", "cidade", "uf",
                  "id_evento", "nome_evento", "setor", "tipo_ingresso", "quantidade",
                  "preco_unitario", "subtotal_pedido", "desconto_pedido", "cupom",
                  "taxa_conveniencia", "valor_total", "forma_pagamento", "parcelas"]
COLUNAS_NOVO = [c if c != "valor_total" else "valor_total_brl" for c in COLUNAS_ANTIGO] + ["id_promotor"]
COLUNAS_EVENTOS = ["id_evento", "nome_evento", "artista", "categoria", "local", "cidade", "uf",
                   "capacidade", "data_evento", "abertura_vendas", "status_evento", "atualizado_em"]


# --------------------------------------------------------------------------
# Utilitários
# --------------------------------------------------------------------------
def escolher(rng, pares):
    """Escolha ponderada a partir de [(valor, peso), ...]."""
    valores, pesos = zip(*pares)
    return rng.choices(valores, weights=pesos, k=1)[0]


def meses_entre(inicio, fim):
    a, m = map(int, inicio.split("-"))
    fa, fm = map(int, fim.split("-"))
    saida = []
    while (a, m) <= (fa, fm):
        saida.append(f"{a:04d}-{m:02d}")
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return saida


def num_br(valor, rng=None, permitir_rs=False):
    """Formata como os arquivos originais: vírgula decimal, sem zeros à direita.
    Com permitir_rs, às vezes devolve 'R$ 1.234,50'."""
    if permitir_rs and rng is not None and rng.random() < 0.035:
        inteiro, dec = f"{valor:,.2f}".split(".")
        return f"R$ {inteiro.replace(',', '.')},{dec}"
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def gerar_cpf(rng):
    base = [rng.randint(0, 9) for _ in range(9)]
    for n in (10, 11):
        soma = sum(d * p for d, p in zip(base, range(n, 1, -1)))
        dv = (soma * 10) % 11
        base.append(0 if dv == 10 else dv)
    return "".join(map(str, base))


def nulo_texto(rng, extras=()):
    return rng.choice(["", "NULL", "null"] + list(extras))


# --------------------------------------------------------------------------
# Catálogo de eventos
# --------------------------------------------------------------------------
def gerar_catalogo(rng, inicio):
    a, m = map(int, inicio.split("-"))
    base = date(a, m, 1)
    eventos = []
    categorias = ["SHOW"] * 108 + ["TEATRO"] * 23 + ["FESTIVAL"] * 12 + ["ESPORTE"] * 7
    rng.shuffle(categorias)
    for i, cat in enumerate(categorias, start=1):
        if cat == "SHOW":
            artista = rng.choice(ARTISTAS)
            nome = artista if rng.random() < 0.1 else f"{artista} - Turnê {rng.choice(TURNES)}"
            local = rng.choice([l for l in LOCAIS if l[3] in ("arena", "parque")])
        elif cat == "TEATRO":
            artista = f"Cia. {rng.choice(SOBRENOMES)}"
            nome = rng.choice(PECAS)
            local = rng.choice([l for l in LOCAIS if l[3] == "teatro"])
        elif cat == "FESTIVAL":
            artista = "Vários"
            nome = rng.choice(FESTIVAIS)
            local = rng.choice([l for l in LOCAIS if l[3] in ("parque", "arena")])
        else:
            artista = ""
            mandante, visitante = rng.sample(TIMES, 2)
            nome = f"{mandante} x {visitante}"
            local = rng.choice([l for l in LOCAIS if l[3] in ("estadio", "arena")])
        capacidade = {"teatro": rng.choice([1200, 1500, 1800, 2200]),
                      "estadio": rng.choice([45000, 60000]),
                      "parque": rng.choice([30000, 40000, 50000])}.get(local[3], rng.choice([7000, 12000, 18000, 20000, 22000]))
        data_evento = base + timedelta(days=rng.randint(10, 480))
        abertura = data_evento - timedelta(days=rng.randint(30, 150))
        eventos.append({
            "id_evento": f"EV-{i:04d}", "nome": nome, "artista": artista, "categoria": cat,
            "local": local[0], "cidade": local[1], "uf": local[2], "capacidade": capacidade,
            "data_evento": data_evento, "abertura": abertura,
            "atualizado_em": datetime(abertura.year, abertura.month, abertura.day, 9, 0, tzinfo=TZ_BR),
            "popularidade": rng.paretovariate(1.6),
            "fator_preco": rng.uniform(0.7, 1.6),
            # sujeira fixa do cadastro
            "nome_sujo": rng.random() < 0.10, "categoria_minuscula": rng.random() < 0.05,
            "capacidade_ponto": rng.random() < 0.14, "data_br": rng.random() < 0.11,
            "adiamento": None,
        })
    # alguns eventos são adiados (SCD2): a data muda num momento do período
    for ev in rng.sample(eventos, 8):
        ev["adiamento"] = {
            "quando": ev["data_evento"] - timedelta(days=rng.randint(5, 40)),
            "nova_data": ev["data_evento"] + timedelta(days=rng.randint(30, 110)),
        }
    return eventos


def estado_evento(ev, dia):
    """Data do evento e status vistos num determinado dia (respeitando adiamentos)."""
    data_ev, atualizado, adiado = ev["data_evento"], ev["atualizado_em"], False
    ad = ev["adiamento"]
    if ad and dia >= ad["quando"]:
        data_ev, adiado = ad["nova_data"], True
        q = ad["quando"]
        atualizado = datetime(q.year, q.month, q.day, 10, 0, tzinfo=TZ_BR)
    if data_ev < dia:
        status = "REALIZADO"
    elif adiado:
        status = "ADIADO"
    else:
        status = "A_REALIZAR"
    return data_ev, status, atualizado


def linhas_eventos(rng, eventos, dia, estresse):
    saida = []
    for ev in eventos:
        if ev["abertura"] > dia + timedelta(days=200):
            continue
        data_ev, status, atualizado = estado_evento(ev, dia)
        nome = f"  {ev['nome'].upper()}" if ev["nome_sujo"] else ev["nome"]
        artista = ev["artista"] if ev["artista"] else nulo_texto(rng)
        capacidade = f"{ev['capacidade']:,}".replace(",", ".") if ev["capacidade_ponto"] else str(ev["capacidade"])
        data_txt = data_ev.strftime("%d/%m/%Y") if ev["data_br"] else data_ev.isoformat()
        if estresse and rng.random() < 0.03:
            data_txt = data_ev.strftime("%Y/%m/%d")  # formato novo
        saida.append({
            "id_evento": ev["id_evento"], "nome_evento": nome, "artista": artista,
            "categoria": ev["categoria"].lower() if ev["categoria_minuscula"] else ev["categoria"],
            "local": ev["local"], "cidade": ev["cidade"], "uf": ev["uf"], "capacidade": capacidade,
            "data_evento": data_txt, "abertura_vendas": ev["abertura"].isoformat(),
            "status_evento": status, "atualizado_em": atualizado.isoformat(),
        })
    return saida


# --------------------------------------------------------------------------
# Clientes
# --------------------------------------------------------------------------
def gerar_clientes(rng, n):
    clientes = []
    for i in range(1, n + 1):
        primeiro = rng.choice(NOMES)
        s1, s2 = rng.choice(SOBRENOMES), rng.choice(SOBRENOMES)
        cidade, uf, _ = rng.choices(CIDADES, weights=[c[2] for c in CIDADES], k=1)[0]
        usuario = f"{primeiro.lower().translate(SEM_ACENTO)}.{s1.lower().translate(SEM_ACENTO)}{rng.randint(1, 999)}"
        nasc = date(1955, 1, 1) + timedelta(days=rng.randint(0, 18250))
        clientes.append({
            "id_cliente": f"CL-{i:06d}", "nome": f"{primeiro} {s1} {s2}", "cpf": gerar_cpf(rng),
            "email": f"{usuario}@{rng.choice(DOMINIOS)}", "nascimento": nasc.isoformat(),
            "cidade": cidade, "uf": uf,
        })
    return clientes


# --------------------------------------------------------------------------
# Pedidos
# --------------------------------------------------------------------------
def gerar_pedidos_mes(rng, mes, eh_ultimo, eventos, clientes, pedidos_por_dia, dias_ultimo_mes):
    """Gera os pedidos 'limpos' de um mês (a verdade). A sujeira é aplicada na escrita."""
    pedidos = []
    ano, m = map(int, mes.split("-"))
    dias = calendar.monthrange(ano, m)[1]
    if eh_ultimo and dias_ultimo_mes:
        dias = min(dias, dias_ultimo_mes)
    for d in range(1, dias + 1):
        dia = date(ano, m, d)
        disponiveis = [e for e in eventos if e["abertura"] <= dia <= estado_evento(e, dia)[0]]
        if not disponiveis:
            continue
        pesos = [e["popularidade"] for e in disponiveis]
        qtd = max(1, int(rng.gauss(pedidos_por_dia, pedidos_por_dia * 0.06)))
        for n in range(1, qtd + 1):
            pedidos.append(montar_pedido(rng, dia, n, disponiveis, pesos, clientes))
    return pedidos


def montar_pedido(rng, dia, n, disponiveis, pesos, clientes):
    segundos = int(rng.triangular(0, 86399, 20 * 3600))
    criado = datetime(dia.year, dia.month, dia.day, tzinfo=TZ_BR) + timedelta(seconds=segundos)
    atualizado = criado + timedelta(seconds=rng.randint(20, 900))
    cliente = rng.choice(clientes)
    canal = escolher(rng, CANAIS)
    forma = escolher(rng, PAGAMENTO_CANAL[canal])
    parcelas = escolher(rng, PARCELAS_CREDITO) if forma == "CARTAO_CREDITO" else 1
    status = escolher(rng, [("APROVADO", 92.0), ("RECUSADO", 5.0), ("PENDENTE", 3.0)])
    evento = rng.choices(disponiveis, weights=pesos, k=1)[0]
    cortesia_total = rng.random() < 0.025
    n_itens = escolher(rng, [(1, 74), (2, 21), (3, 5)])
    itens = []
    for seq in range(1, n_itens + 1):
        setor, base, _ = rng.choices(SETORES[evento["categoria"]], weights=[s[2] for s in SETORES[evento["categoria"]]], k=1)[0]
        if cortesia_total:
            tipo = "CORTESIA"
        else:
            tipo = escolher(rng, [("INTEIRA", 64), ("MEIA", 36)])
        preco_inteira = round(base * evento["fator_preco"] * FATOR_MES[dia.month] / 0.4) * 0.4
        preco = 0.0 if tipo == "CORTESIA" else (preco_inteira / 2 if tipo == "MEIA" else preco_inteira)
        itens.append({"seq": seq, "setor": setor, "tipo": tipo, "quantidade": escolher(rng, [(1, 45), (2, 40), (3, 8), (4, 7)]),
                      "preco": round(preco, 2)})
    # cortesia "de brinde" dentro de um pedido pago
    if not cortesia_total and rng.random() < 0.02:
        itens.append({"seq": len(itens) + 1, "setor": itens[0]["setor"], "tipo": "CORTESIA",
                      "quantidade": escolher(rng, [(1, 50), (2, 50)]), "preco": 0.0})
    subtotal = round(sum(i["preco"] * i["quantidade"] for i in itens), 2)
    cupom = rng.choice(list(CUPONS)) if (not cortesia_total and rng.random() < 0.07) else None
    desconto = round(subtotal * CUPONS[cupom], 2) if cupom else 0.0
    taxa = round(subtotal * TAXA_CANAL[canal], 2)
    total = round(subtotal - desconto + taxa, 2)
    if status in ("RECUSADO", "PENDENTE"):
        atualizado = criado + timedelta(seconds=rng.randint(20, 600))
    return {
        "id": f"TK-{dia.strftime('%Y%m%d')}-{n:05d}", "criado": criado, "atualizado": atualizado,
        "status": status, "canal": canal, "forma": forma, "parcelas": parcelas, "cliente": cliente,
        "evento": evento, "itens": itens, "subtotal": subtotal, "desconto": desconto, "cupom": cupom,
        "taxa": taxa, "total": total, "promotor": f"PR-{min(25, int(rng.paretovariate(0.9))):03d}",
    }


# --------------------------------------------------------------------------
# Sujeira (aplicada linha a linha, na escrita)
# --------------------------------------------------------------------------
def sujar_data_pedido(rng, criado, estresse):
    r = rng.random()
    if estresse and r < 0.01:
        return criado.strftime("%Y-%m-%d %H:%M:%S")                       # formato NOVO
    if r < 0.05:
        return criado.strftime("%d/%m/%Y %H:%M:%S")                       # local, sem fuso
    if r < 0.08:
        utc = criado.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
    if r < 0.11:
        return str(int(criado.timestamp() * 1000))                         # epoch em ms
    return criado.isoformat()


def sujar_cidade(rng, cidade, estresse):
    r = rng.random()
    if estresse and r < 0.005:
        return {"São Paulo": "S.Paulo", "Rio de Janeiro": "Rio", "Belo Horizonte": "BH"}.get(cidade, cidade)
    if cidade == "São Paulo" and r < 0.012:
        return rng.choice(["S. Paulo", "Sampa", "SAO PAULO - SP"])
    if r < 0.07:
        return cidade.translate(SEM_ACENTO)
    if r < 0.10:
        return cidade.upper()
    if r < 0.11:
        return cidade + " "
    return cidade


def sujar_linha(rng, ped, item, schema_novo, estresse):
    extras = ("NA", "-", "N/D") if estresse else ()
    cli = ped["cliente"]

    def nulo():
        return nulo_texto(rng, extras if rng.random() < 0.3 else ())

    status = ped["status"]
    if rng.random() < 0.04:
        status = status.title()
    if estresse and rng.random() < 0.005:
        status = status + " "

    canal = ped["canal"]
    r = rng.random()
    if r < 0.04:
        canal = rng.choice(["N/A", "", "null", "NULL"] + list(extras))
    elif r < 0.07:
        canal = canal.lower()

    cpf = cli["cpf"]
    r = rng.random()
    if r < 0.03:
        cpf = nulo()
    elif r < 0.45:
        if cpf.startswith("0") and rng.random() < 0.25:
            cpf = cpf[1:]                                                  # perdeu o zero
    else:
        cpf = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"

    email = cli["email"]
    r = rng.random()
    if r < 0.0025:
        email = "n/a"
    elif r < 0.005:
        email = "sem-email"
    elif r < 0.0075:
        email = "teste@"
    elif estresse and r < 0.010:
        email = rng.choice(extras)
    elif r < 0.06:
        email = rng.choice([" " + email, email + " "])
    elif r < 0.08:
        email = email.upper()

    uf = cli["uf"].lower() if rng.random() < 0.05 else cli["uf"]

    id_evento = ped["evento"]["id_evento"]
    if rng.random() < 0.005:
        id_evento = f"EV-{rng.randint(9000, 9999)}"                       # evento órfão

    quantidade = item["quantidade"]
    if rng.random() < 0.0023:
        quantidade = rng.choice([0, -1, -2])

    cupom = ped["cupom"] if ped["cupom"] else nulo_texto(rng)

    usar_ponto = estresse and rng.random() < 0.01
    def valor(v, rs=False):
        texto = num_br(v, rng, permitir_rs=rs)
        return texto.replace(",", ".") if usar_ponto and "R$" not in texto else texto

    linha = {
        "id_pedido": ped["id"], "item_seq": item["seq"],
        "data_pedido": sujar_data_pedido(rng, ped["criado"], estresse),
        "data_atualizacao": ped["atualizado"].isoformat(),
        "status": status, "canal": canal, "id_cliente": cli["id_cliente"], "nome_cliente": cli["nome"],
        "cpf": cpf, "email": email, "data_nascimento": cli["nascimento"],
        "cidade": sujar_cidade(rng, cli["cidade"], estresse), "uf": uf,
        "id_evento": id_evento, "nome_evento": ped["evento"]["nome"], "setor": item["setor"],
        "tipo_ingresso": item["tipo"], "quantidade": quantidade, "preco_unitario": valor(item["preco"]),
        "subtotal_pedido": valor(ped["subtotal"]), "desconto_pedido": valor(ped["desconto"]),
        "cupom": cupom, "taxa_conveniencia": valor(ped["taxa"]),
        "forma_pagamento": ped["forma"], "parcelas": ped["parcelas"],
    }
    if schema_novo:
        linha["valor_total_brl"] = valor(ped["total"], rs=True)
        linha["id_promotor"] = ped["promotor"]
    else:
        linha["valor_total"] = valor(ped["total"], rs=True)
    return linha


# --------------------------------------------------------------------------
# Distribuição das linhas pelos arquivos mensais
# --------------------------------------------------------------------------
def distribuir_mes(rng, pedidos, mes, meses, pendentes):
    """Decide em qual arquivo cada versão de pedido cai.
    Pedidos atrasados e mudanças de status posteriores vão para 'pendentes',
    que guarda o que deve entrar nos arquivos dos meses seguintes."""
    lote = pendentes.pop(mes, [])
    i = meses.index(mes)
    for ped in pedidos:
        destino = mes
        if rng.random() < 0.009 and i + 1 < len(meses):                     # chegou atrasado
            destino = meses[i + 1]
        (lote if destino == mes else pendentes.setdefault(destino, [])).append(ped)
        # mudança de status dias depois (APROVADO -> CANCELADO/ESTORNADO)
        if ped["status"] == "APROVADO" and rng.random() < 0.031:
            novo = dict(ped)
            novo["status"] = "CANCELADO" if rng.random() < 0.70 else "ESTORNADO"
            novo["atualizado"] = ped["atualizado"] + timedelta(days=rng.randint(0, 20), seconds=rng.randint(3600, 80000))
            mes_novo = max(novo["atualizado"].strftime("%Y-%m"), destino)
            if mes_novo == mes:
                lote.append(novo)
            elif mes_novo in meses:
                pendentes.setdefault(mes_novo, []).append(novo)
    return lote


def escrever_vendas_mes(rng, lote, mes, meses, saida, corte, meses_iso, estresse):
    mes_encoding_trocado = meses[len(meses) // 2] if estresse else None
    mes_colunas_trocadas = meses[len(meses) // 3] if estresse else None
    schema_novo = mes >= corte
    colunas = list(COLUNAS_NOVO if schema_novo else COLUNAS_ANTIGO)
    if mes == mes_colunas_trocadas:
        colunas[5], colunas[6] = colunas[6], colunas[5]                    # canal <-> id_cliente
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=colunas, delimiter=";", lineterminator="\r\n",
                       quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
    w.writeheader()
    for ped in lote:
        for item in ped["itens"]:
            linha = sujar_linha(rng, ped, item, schema_novo, estresse)
            w.writerow(linha)
            r = rng.random()
            if r < 0.0037:
                w.writerow(linha)                                          # cópia exata
            elif r < 0.010:
                w.writerow(sujar_linha(rng, ped, item, schema_novo, estresse))  # cópia "disfarçada"
    texto = buf.getvalue()
    iso = mes in meses_iso or mes == mes_encoding_trocado
    dados = texto.encode("latin-1", errors="replace") if iso else texto.encode("utf-8-sig")
    caminho = os.path.join(saida, f"vendas_{mes}.csv.gz")
    with gzip.GzipFile(caminho, "wb", mtime=0) as f:                       # mtime=0: arquivo idêntico a cada execução
        f.write(dados)
    return caminho, texto.count("\r\n") - 1


def escrever_eventos(rng, eventos, meses, saida, estresse):
    for mes in meses:
        ano, m = map(int, mes.split("-"))
        buf = io.StringIO(newline="")
        w = csv.DictWriter(buf, fieldnames=COLUNAS_EVENTOS, delimiter=";", lineterminator="\n")
        w.writeheader()
        w.writerows(linhas_eventos(rng, eventos, date(ano, m, 1), estresse))
        with open(os.path.join(saida, f"eventos_{mes}.csv"), "wb") as f:
            f.write(buf.getvalue().encode("utf-8-sig"))


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Gera dados sintéticos de vendas de ingressos.")
    p.add_argument("--semente", type=int, default=42)
    p.add_argument("--inicio", default="2025-10")
    p.add_argument("--fim", default="2026-10")
    p.add_argument("--dias-ultimo-mes", type=int, default=7, help="0 = mês completo")
    p.add_argument("--pedidos-por-dia", type=int, default=1850)
    p.add_argument("--clientes", type=int, default=40000)
    p.add_argument("--corte-esquema", default="2026-06")
    p.add_argument("--meses-iso", default="2026-01,2026-02")
    p.add_argument("--modo", choices=["normal", "estresse"], default="normal")
    p.add_argument("--saida", default="saida")
    a = p.parse_args()

    os.makedirs(a.saida, exist_ok=True)
    rng = random.Random(a.semente)
    estresse = a.modo == "estresse"
    meses = meses_entre(a.inicio, a.fim)

    eventos = gerar_catalogo(rng, a.inicio)
    clientes = gerar_clientes(rng, a.clientes)
    meses_iso = [m.strip() for m in a.meses_iso.split(",") if m.strip()]

    pendentes, total_pedidos, arquivos = {}, 0, []
    for idx, mes in enumerate(meses):
        pedidos = gerar_pedidos_mes(rng, mes, idx == len(meses) - 1, eventos, clientes,
                                    a.pedidos_por_dia, a.dias_ultimo_mes)
        total_pedidos += len(pedidos)
        lote = distribuir_mes(rng, pedidos, mes, meses, pendentes)
        arquivos.append(escrever_vendas_mes(rng, lote, mes, meses, a.saida, a.corte_esquema,
                                            meses_iso, estresse))
    escrever_eventos(rng, eventos, meses, a.saida, estresse)

    print(f"Semente {a.semente} | modo {a.modo} | {total_pedidos} pedidos")
    for caminho, linhas in arquivos:
        print(f"  {os.path.basename(caminho)}: {linhas} linhas")


if __name__ == "__main__":
    main()
