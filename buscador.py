#!/usr/bin/env python3
"""Buscador diário de passagens com milhas Smiles (Brasil -> Europa).

Lê as rotas e filtros de config.yaml, pesquisa cada combinação de
origem/destino/data na Smiles, guarda os resultados em dados/ e avisa
por Telegram e/ou e-mail quando encontra ofertas dentro do limite de milhas.

Uso:
    python buscador.py                     # busca e notifica
    python buscador.py --sem-notificar     # só busca e salva
    python buscador.py --testar-notificacao
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import smtplib
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent
PASTA_DADOS = RAIZ / "dados"
ARQUIVO_ESTADO = PASTA_DADOS / "vistos.json"

URL_API = "https://api-air-flightsearch-prd.smiles.com.br/v1/airlines/search"
# Chave pública usada pelo próprio site da Smiles (não é uma credencial sua).
CHAVE_API_PADRAO = "aJqPU7xNHl9qN3NVZnPaJ208aPo2Bh2p2ZV844tw"
URL_SITE_BUSCA = "https://www.smiles.com.br/mfe/emissao-passagem/"

CABECALHOS_API = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
    "channel": "WEB",
    "language": "pt-BR",
    "region": "BRASIL",
    "origin": "https://www.smiles.com.br",
    "referer": "https://www.smiles.com.br/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
}

MAX_ERROS_SEGUIDOS = 5

TARIFAS_SO_MILHAS = {False: ("SMILES",), True: ("SMILES_CLUB", "SMILES")}


class BloqueadoError(Exception):
    """A Smiles recusou a requisição (proteção anti-robô)."""


@dataclass
class Consulta:
    sentido: str  # "ida" ou "volta"
    origem: str
    destino: str
    data: date


@dataclass
class Oferta:
    sentido: str
    origem: str
    destino: str
    data: str
    partida: str
    chegada: str
    companhia: str
    voos: str
    paradas: int
    duracao: str
    cabine: str
    milhas: int
    tarifa: str

    @property
    def chave(self) -> str:
        return f"{self.sentido}|{self.origem}|{self.destino}|{self.data}"


# ---------------------------------------------------------------- configuração


def carregar_config(caminho: Path) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def gerar_datas(cfg_datas: dict, hoje: date) -> list[date]:
    passo = max(1, int(cfg_datas.get("intervalo_dias", 1)))
    if cfg_datas.get("inicio"):
        inicio = _para_data(cfg_datas["inicio"])
        fim = _para_data(cfg_datas.get("fim") or cfg_datas["inicio"])
    else:
        inicio = hoje + timedelta(days=int(cfg_datas.get("dias_a_partir_de_hoje", 1)))
        fim = inicio + timedelta(days=int(cfg_datas.get("janela_dias", 30)))
    inicio = max(inicio, hoje + timedelta(days=1))
    datas = []
    atual = inicio
    while atual <= fim:
        datas.append(atual)
        atual += timedelta(days=passo)
    return datas


def _para_data(valor) -> date:
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor))


def gerar_consultas(cfg: dict, hoje: date) -> list[Consulta]:
    origens = [o.upper() for o in cfg.get("origens", [])]
    destinos = [d.upper() for d in cfg.get("destinos", [])]
    datas = gerar_datas(cfg.get("datas", {}), hoje)
    consultas = [
        Consulta("ida", o, d, dt) for dt in datas for o in origens for d in destinos
    ]
    volta = cfg.get("volta") or {}
    if volta.get("ativa"):
        duracao = timedelta(days=int(volta.get("duracao_viagem_dias", 14)))
        consultas += [
            Consulta("volta", d, o, dt + duracao)
            for dt in datas
            for o in origens
            for d in destinos
        ]
    return consultas


# ---------------------------------------------------------------- busca


class ClienteSmiles:
    def __init__(self, modo: str = "auto", cabine: str = "all", adultos: int = 1):
        self.modo = modo
        self.cabine = cabine
        self.adultos = adultos
        self._sessao = None
        self._navegador = None

    def buscar(self, origem: str, destino: str, dia: date) -> dict:
        if self.modo in ("api", "auto"):
            try:
                return self._buscar_api(origem, destino, dia)
            except BloqueadoError:
                if self.modo == "api":
                    raise
                print("  API bloqueada; mudando para o modo navegador.", file=sys.stderr)
                self.modo = "navegador"
        return self._buscar_navegador(origem, destino, dia)

    # --- modo API ---------------------------------------------------------

    def _parametros(self, origem: str, destino: str, dia: date) -> dict:
        return {
            "cabinType": self.cabine,
            "originAirportCode": origem,
            "destinationAirportCode": destino,
            "departureDate": dia.isoformat(),
            "memberNumber": "",
            "adults": self.adultos,
            "children": 0,
            "infants": 0,
            "forceCongener": "false",
        }

    def _buscar_api(self, origem: str, destino: str, dia: date) -> dict:
        if self._sessao is None:
            # curl_cffi imita a "impressão digital" TLS do Chrome, o que reduz bloqueios.
            from curl_cffi import requests as cffi_requests

            self._sessao = cffi_requests.Session(impersonate="chrome")
        cabecalhos = dict(CABECALHOS_API)
        cabecalhos["x-api-key"] = os.environ.get("SMILES_API_KEY", CHAVE_API_PADRAO)

        for tentativa in range(3):
            resp = self._sessao.get(
                URL_API,
                params=self._parametros(origem, destino, dia),
                headers=cabecalhos,
                timeout=45,
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (403, 406):
                raise BloqueadoError(f"HTTP {resp.status_code}")
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (tentativa + 1))
                continue
            # 400/404 costumam significar rota sem voos naquele dia.
            return {}
        raise RuntimeError(f"Falha ao buscar {origem}-{destino} {dia}: HTTP {resp.status_code}")

    # --- modo navegador -----------------------------------------------------

    def _abrir_navegador(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        caminho = os.environ.get("CHROMIUM_PATH")
        self._navegador = self._pw.chromium.launch(
            headless=os.environ.get("MOSTRAR_NAVEGADOR") != "1",
            executable_path=caminho or None,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._contexto = self._navegador.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            user_agent=CABECALHOS_API["user-agent"],
            viewport={"width": 1366, "height": 850},
        )
        self._pagina = self._contexto.new_page()
        self._pagina.goto("https://www.smiles.com.br/home", wait_until="domcontentloaded", timeout=60000)
        self._pagina.wait_for_timeout(3000)

    def _buscar_navegador(self, origem: str, destino: str, dia: date) -> dict:
        if self._navegador is None:
            self._abrir_navegador()
        meio_dia_brt = datetime(dia.year, dia.month, dia.day, 12, tzinfo=timezone(timedelta(hours=-3)))
        params = {
            "adults": self.adultos,
            "cabin": self.cabine.upper() if self.cabine != "all" else "ALL",
            "children": 0,
            "departureDate": int(meio_dia_brt.timestamp() * 1000),
            "infants": 0,
            "isElegible": "false",
            "isFlexibleDateChecked": "false",
            "returnDate": "",
            "searchType": "congenere",
            "segments": 1,
            "tripType": 2,
            "originAirport": origem,
            "originAirportIsAny": "false",
            "destinationAirport": destino,
            "destinAirportIsAny": "false",
            "novo-resultado-voos": "true",
        }
        url = URL_SITE_BUSCA + "?" + urllib.parse.urlencode(params)

        def eh_resposta_da_busca(r) -> bool:
            return (
                "/v1/airlines/search" in r.url
                and f"originAirportCode={origem}" in r.url
                and f"destinationAirportCode={destino}" in r.url
            )

        try:
            with self._pagina.expect_response(eh_resposta_da_busca, timeout=90000) as info:
                self._pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
            resp = info.value
        except Exception as e:  # timeout: página não chegou a pesquisar
            raise RuntimeError(f"Navegador não obteve resultado para {origem}-{destino} {dia}: {e}") from e
        if resp.status in (403, 406):
            raise BloqueadoError(f"HTTP {resp.status} no navegador")
        if resp.status != 200:
            return {}
        return resp.json()

    def fechar(self):
        if self._navegador is not None:
            self._navegador.close()
            self._pw.stop()


# ---------------------------------------------------------------- interpretação


def extrair_ofertas(resposta: dict, consulta: Consulta, clube: bool = False) -> list[Oferta]:
    ofertas = []
    for segmento in resposta.get("requestedFlightSegmentList") or []:
        for voo in segmento.get("flightList") or []:
            tarifa = _melhor_tarifa_em_milhas(voo.get("fareList") or [], clube)
            if tarifa is None:
                continue
            partida = voo.get("departure") or {}
            chegada = voo.get("arrival") or {}
            pernas = voo.get("legList") or []
            ofertas.append(
                Oferta(
                    sentido=consulta.sentido,
                    origem=(partida.get("airport") or {}).get("code") or consulta.origem,
                    destino=(chegada.get("airport") or {}).get("code") or consulta.destino,
                    data=consulta.data.isoformat(),
                    partida=partida.get("date", ""),
                    chegada=chegada.get("date", ""),
                    companhia=(voo.get("airline") or {}).get("name", ""),
                    voos=" / ".join(_numero_voo(p) for p in pernas) or "",
                    paradas=int(voo.get("stops") or max(len(pernas) - 1, 0)),
                    duracao=_duracao(voo.get("duration")),
                    cabine=voo.get("cabin", ""),
                    milhas=int(tarifa["miles"]),
                    tarifa=tarifa.get("type", ""),
                )
            )
    return ofertas


def _melhor_tarifa_em_milhas(tarifas: list[dict], clube: bool) -> dict | None:
    candidatas = [
        t
        for t in tarifas
        if t.get("type") in TARIFAS_SO_MILHAS[clube] and (t.get("miles") or 0) > 0
    ]
    return min(candidatas, key=lambda t: t["miles"], default=None)


def _numero_voo(perna: dict) -> str:
    cia = (perna.get("marketingAirline") or perna.get("operationAirline") or {}).get("code", "")
    return f"{cia}{perna.get('flightNumber', '')}".strip()


def _duracao(d) -> str:
    if isinstance(d, dict):
        return f"{d.get('hours', 0)}h{int(d.get('minutes', 0)):02d}"
    return str(d or "")


def filtrar(ofertas: list[Oferta], cfg: dict) -> list[Oferta]:
    max_milhas = cfg.get("max_milhas")
    max_paradas = cfg.get("max_paradas")
    companhias = {c.upper() for c in cfg.get("companhias") or []}
    cabine = str(cfg.get("cabine", "all")).upper()
    resultado = []
    for o in ofertas:
        if max_milhas and o.milhas > max_milhas:
            continue
        if max_paradas is not None and o.paradas > max_paradas:
            continue
        if cabine != "ALL" and o.cabine and o.cabine.upper() != cabine:
            continue
        if companhias and not any(v[:2] in companhias for v in o.voos.split(" / ")):
            continue
        resultado.append(o)
    return resultado


def melhor_por_rota_e_dia(ofertas: list[Oferta]) -> list[Oferta]:
    melhores: dict[str, Oferta] = {}
    for o in ofertas:
        atual = melhores.get(o.chave)
        if atual is None or o.milhas < atual.milhas:
            melhores[o.chave] = o
    return sorted(melhores.values(), key=lambda o: (o.milhas, o.data))


# ---------------------------------------------------------------- persistência


def carregar_estado() -> dict:
    if ARQUIVO_ESTADO.exists():
        return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    return {}


def separar_novidades(ofertas: list[Oferta], estado: dict) -> list[Oferta]:
    """Ofertas que não existiam ou ficaram mais baratas desde a última busca."""
    return [o for o in ofertas if o.chave not in estado or o.milhas < estado[o.chave]]


def salvar_estado(ofertas: list[Oferta], hoje: date):
    # Guarda só o retrato atual, descartando datas que já passaram.
    estado = {o.chave: o.milhas for o in ofertas if o.data >= hoje.isoformat()}
    PASTA_DADOS.mkdir(exist_ok=True)
    ARQUIVO_ESTADO.write_text(json.dumps(estado, indent=1, sort_keys=True), encoding="utf-8")


def salvar_csv(ofertas: list[Oferta], hoje: date) -> Path:
    pasta = PASTA_DADOS / "resultados"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{hoje.isoformat()}.csv"
    campos = list(Oferta.__dataclass_fields__)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        for o in ofertas:
            escritor.writerow(asdict(o))
    return caminho


# ---------------------------------------------------------------- notificação


def montar_mensagem(ofertas: list[Oferta], total: int, max_itens: int) -> str:
    if not ofertas:
        return "✈️ Buscador Smiles: nenhuma oferta nova dentro do limite de milhas hoje."
    linhas = [f"✈️ Buscador Smiles: {total} oferta(s) para a Europa\n"]
    for sentido in ("ida", "volta"):
        do_sentido = [o for o in ofertas if o.sentido == sentido][:max_itens]
        if not do_sentido:
            continue
        linhas.append("IDA (Brasil → Europa)" if sentido == "ida" else "VOLTA (Europa → Brasil)")
        for o in do_sentido:
            dia = date.fromisoformat(o.data).strftime("%d/%m/%Y")
            paradas = "direto" if o.paradas == 0 else f"{o.paradas} parada(s)"
            milhas = f"{o.milhas:,}".replace(",", ".")
            linhas.append(
                f"• {milhas} milhas — {o.origem}→{o.destino} em {dia} "
                f"({o.companhia}, {paradas}, {o.duracao})"
            )
        linhas.append("")
    linhas.append("Taxas de embarque não incluídas. Confira e emita em smiles.com.br")
    return "\n".join(linhas)


def enviar_telegram(texto: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    dados = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": texto[:4000], "disable_web_page_preview": "true"}
    ).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with urllib.request.urlopen(url, data=dados, timeout=30) as r:
        return r.status == 200


def enviar_email(assunto: str, texto: str, anexo: Path | None = None) -> bool:
    usuario = os.environ.get("SMTP_USUARIO")
    senha = os.environ.get("SMTP_SENHA")
    para = os.environ.get("EMAIL_PARA") or usuario
    if not (usuario and senha):
        return False
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = usuario
    msg["To"] = para
    msg.set_content(texto)
    if anexo and anexo.exists():
        msg.add_attachment(anexo.read_bytes(), maintype="text", subtype="csv", filename=anexo.name)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    porta = int(os.environ.get("SMTP_PORTA", "465"))
    with smtplib.SMTP_SSL(host, porta, timeout=30) as smtp:
        smtp.login(usuario, senha)
        smtp.send_message(msg)
    return True


def notificar(texto: str, assunto: str, anexo: Path | None = None):
    enviados = []
    canais = (
        ("Telegram", lambda: enviar_telegram(texto)),
        ("e-mail", lambda: enviar_email(assunto, texto, anexo)),
    )
    for nome, envio in canais:
        try:
            if envio():
                enviados.append(nome)
        except Exception as e:
            print(f"Falha ao enviar {nome}: {e}", file=sys.stderr)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write("```\n" + texto + "\n```\n")
    print(f"Notificação enviada por: {', '.join(enviados) or 'nenhum canal configurado'}")


# ---------------------------------------------------------------- principal


def executar(cfg: dict, notificar_ao_fim: bool = True) -> int:
    hoje = date.today()
    consultas = gerar_consultas(cfg, hoje)
    print(f"{len(consultas)} buscas a fazer.")
    cliente = ClienteSmiles(
        modo=cfg.get("modo", "auto"),
        cabine=cfg.get("cabine", "all"),
        adultos=int(cfg.get("adultos", 1)),
    )
    pausa = float(cfg.get("pausa_entre_buscas_seg", 4))
    todas: list[Oferta] = []
    sucessos = 0
    erros_seguidos = 0
    try:
        for i, c in enumerate(consultas, 1):
            print(f"[{i}/{len(consultas)}] {c.sentido} {c.origem}-{c.destino} {c.data}")
            try:
                resposta = cliente.buscar(c.origem, c.destino, c.data)
                todas += extrair_ofertas(resposta, c, bool(cfg.get("clube_smiles")))
                sucessos += 1
                erros_seguidos = 0
            except BloqueadoError as e:
                print(f"Bloqueado pela Smiles ({e}). Interrompendo.", file=sys.stderr)
                break
            except Exception as e:
                erros_seguidos += 1
                print(f"  erro: {e}", file=sys.stderr)
                if erros_seguidos >= MAX_ERROS_SEGUIDOS:
                    print(f"{erros_seguidos} erros seguidos. Interrompendo.", file=sys.stderr)
                    break
            time.sleep(pausa + random.uniform(0, pausa / 2))
    finally:
        cliente.fechar()

    if not consultas:
        print("Nenhuma busca gerada; confira origens, destinos e datas no config.yaml.", file=sys.stderr)
        return 1
    if sucessos == 0:
        print("Nenhuma busca funcionou; estado anterior mantido.", file=sys.stderr)
        if notificar_ao_fim:
            notificar(
                "⚠️ Buscador Smiles: todas as buscas falharam hoje (provável bloqueio). "
                "Veja o log da execução.",
                "Buscador Smiles: falha",
            )
        return 1

    ofertas = melhor_por_rota_e_dia(filtrar(todas, cfg))
    caminho = salvar_csv(ofertas, hoje)
    print(f"{len(ofertas)} ofertas dentro dos filtros (salvas em {caminho}).")

    cfg_notif = cfg.get("notificacao") or {}
    estado = carregar_estado()
    a_avisar = separar_novidades(ofertas, estado) if cfg_notif.get("so_novidades", True) else ofertas
    salvar_estado(ofertas, hoje)

    texto = montar_mensagem(a_avisar, len(a_avisar), int(cfg_notif.get("max_itens", 15)))
    print("\n" + texto)
    if notificar_ao_fim and (a_avisar or not cfg_notif.get("so_novidades", True)):
        notificar(texto, f"Smiles: {len(a_avisar)} passagem(ns) para a Europa em milhas", caminho)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(RAIZ / "config.yaml"))
    parser.add_argument("--sem-notificar", action="store_true", help="não envia Telegram/e-mail")
    parser.add_argument("--testar-notificacao", action="store_true", help="envia uma mensagem de teste e sai")
    args = parser.parse_args()

    if args.testar_notificacao:
        notificar("✅ Teste do buscador Smiles: notificações funcionando!", "Buscador Smiles: teste")
        return 0
    return executar(carregar_config(Path(args.config)), notificar_ao_fim=not args.sem_notificar)


if __name__ == "__main__":
    sys.exit(main())
