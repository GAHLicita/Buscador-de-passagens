import json
from datetime import date
from pathlib import Path

import buscador
from buscador import Consulta, Oferta

EXEMPLO = json.loads((Path(__file__).parent / "exemplo_resposta.json").read_text())
CONSULTA = Consulta("ida", "GRU", "LIS", date(2026, 11, 20))


def test_extrai_tarifa_so_em_milhas():
    ofertas = buscador.extrair_ofertas(EXEMPLO, CONSULTA)
    assert [o.milhas for o in ofertas] == [95000, 72000, 250000]
    assert ofertas[0].voos == "TP88"
    assert ofertas[1].voos == "AF457 / AF1124"
    assert ofertas[1].duracao == "17h05"


def test_tarifa_clube():
    ofertas = buscador.extrair_ofertas(EXEMPLO, CONSULTA, clube=True)
    assert [o.milhas for o in ofertas] == [85500, 64800, 250000]


def test_resposta_vazia():
    assert buscador.extrair_ofertas({}, CONSULTA) == []


def test_filtros():
    ofertas = buscador.extrair_ofertas(EXEMPLO, CONSULTA)
    cfg = {"max_milhas": 100000, "max_paradas": 2, "cabine": "ECONOMIC"}
    assert [o.milhas for o in buscador.filtrar(ofertas, cfg)] == [95000, 72000]
    assert [o.milhas for o in buscador.filtrar(ofertas, {**cfg, "max_paradas": 0})] == [95000]
    assert [o.milhas for o in buscador.filtrar(ofertas, {**cfg, "companhias": ["af"]})] == [72000]


def test_melhor_por_rota_e_dia():
    ofertas = buscador.extrair_ofertas(EXEMPLO, CONSULTA)
    melhores = buscador.melhor_por_rota_e_dia(ofertas)
    assert len(melhores) == 1 and melhores[0].milhas == 72000


def test_gerar_datas_relativas():
    datas = buscador.gerar_datas(
        {"dias_a_partir_de_hoje": 10, "janela_dias": 9, "intervalo_dias": 3}, date(2026, 10, 1)
    )
    assert datas == [date(2026, 10, 11), date(2026, 10, 14), date(2026, 10, 17), date(2026, 10, 20)]


def test_gerar_datas_fixas():
    datas = buscador.gerar_datas({"inicio": "2027-01-10", "fim": "2027-01-12"}, date(2026, 10, 1))
    assert datas == [date(2027, 1, 10), date(2027, 1, 11), date(2027, 1, 12)]


def test_consultas_com_volta():
    cfg = {
        "origens": ["gru"],
        "destinos": ["LIS", "MAD"],
        "datas": {"inicio": "2027-01-10", "fim": "2027-01-10"},
        "volta": {"ativa": True, "duracao_viagem_dias": 15},
    }
    consultas = buscador.gerar_consultas(cfg, date(2026, 10, 1))
    assert len(consultas) == 4
    volta = [c for c in consultas if c.sentido == "volta"][0]
    assert (volta.origem, volta.destino, volta.data) == ("LIS", "GRU", date(2027, 1, 25))


def _oferta(milhas, data="2027-01-10"):
    return Oferta("ida", "GRU", "LIS", data, "", "", "TAP", "TP88", 0, "10h30", "ECONOMIC", milhas, "SMILES")


def test_novidades():
    estado = {"ida|GRU|LIS|2027-01-10": 80000}
    assert buscador.separar_novidades([_oferta(80000)], estado) == []
    assert buscador.separar_novidades([_oferta(70000)], estado) == [_oferta(70000)]
    assert buscador.separar_novidades([_oferta(90000, "2027-01-11")], estado) == [_oferta(90000, "2027-01-11")]


def test_mensagem():
    texto = buscador.montar_mensagem([_oferta(72000)], 1, 10)
    assert "72.000 milhas — GRU→LIS em 10/01/2027" in texto
    assert "direto" in texto


def test_carregar_env(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text('# comentário\nSMTP_USUARIO="eu@exemplo.com"\nSMTP_SENHA=abcd efgh\nVAZIO=\nJA_DEFINIDA=nova\n')
    for nome in ("SMTP_USUARIO", "SMTP_SENHA", "VAZIO"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("JA_DEFINIDA", "antiga")
    buscador.carregar_env(arquivo)
    assert buscador.os.environ["SMTP_USUARIO"] == "eu@exemplo.com"
    assert buscador.os.environ["SMTP_SENHA"] == "abcd efgh"
    assert "VAZIO" not in buscador.os.environ
    assert buscador.os.environ["JA_DEFINIDA"] == "antiga"
