"""
SISTEMA DE PROCESSAMENTO E ESTAMPAGEM DE METADADOS GEOGRÁFICOS (v2.0)
-------------------------------------------------------------------
Descrição:
    Este script automatiza a leitura de metadados EXIF (GPS) de imagens (JPG/PNG)
    e gera uma nova versão da fotografia com uma barra informativa inferior.
    O foco principal é a legibilidade em relatórios técnicos, utilizando
    hierarquia visual e compensação de escala para reduções de tamanho.

Funcionalidades Principais:
    - Extração automática de Latitude, Longitude e Altitude.
    - Renderização de barra de dados com alto contraste (Preto/Amarelo/Branco).
    - Ajuste dinâmico de fontes para garantir legibilidade em miniaturas de relatórios.
    - Suporte a processamento em lote (Batch Processing).

Parâmetros de Layout Atuais:
    - BAR_HEIGHT_RATIO: 0.24 (24% da altura da imagem para garantir respiro).
    - LABEL_COLOR: Amarelo Ouro para títulos (Máxima distinção visual).
    - Escalonamento: Fontes compensadas para o campo de Data/Hora.

Requisitos:
    - Pillow (PIL), Matplotlib (para previews), Pathlib.

Copyright (c) 2026 Autor: Tiago Alexandre Batista - DUDJUINA/SEMA
Data: Março de 2026
"""

import sys
import struct
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

# ─────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────
BAR_BG_COLOR     = (0, 0, 0)       # Preto puro para máximo contraste
LABEL_COLOR      = (255, 215, 0)   # Amarelo Ouro (muito mais legível que cinza em miniaturas)
TEXT_COLOR       = (255, 255, 255) # Branco
LINE_COLOR           = (58, 64, 70)
TOP_BORDER_COLOR     = (125, 150, 132)
BOTTOM_BORDER_COLOR  = (28, 32, 36)

BAR_HEIGHT_RATIO     = 0.24
MIN_BAR_HEIGHT       = 110
MAX_BAR_HEIGHT       = 355

JPEG_QUALITY         = 96
PNG_COMPRESS_LEVEL   = 1

APPLY_SHARPEN        = True
SHARPEN_RADIUS       = 1.4
SHARPEN_PERCENT      = 110
SHARPEN_THRESHOLD    = 3

FONT_PATHS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]

EXTENSOES_JPG = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
EXTENSOES_DNG = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf"}
EXTENSOES     = EXTENSOES_JPG | EXTENSOES_DNG

TIFF_TYPES = {
    1:  (1,  "B"),
    2:  (1,  "s"),
    3:  (2,  "H"),
    4:  (4,  "I"),
    5:  (8,  "II"),
    7:  (1,  "B"),
    9:  (4,  "i"),
    10: (8,  "ii"),
}


# ══════════════════════════════════════════════
# EXIF / GPS
# ══════════════════════════════════════════════


def _read_value(data, offset, tiff_type, count, endian):
    if tiff_type not in TIFF_TYPES:
        return None

    unit_size, fmt = TIFF_TYPES[tiff_type]

    if tiff_type == 2:
        return data[offset:offset + count].rstrip(b"\x00").decode("latin-1", errors="replace")

    if tiff_type in (5, 10):
        pfmt = "ii" if tiff_type == 10 else "II"
        vals = []
        for i in range(count):
            n, d = struct.unpack_from(endian + pfmt, data, offset + i * 8)
            vals.append((n, d))
        return vals

    vals = struct.unpack_from(endian + fmt * count, data, offset)
    return vals[0] if count == 1 else list(vals)


def _parse_ifd(data, offset, endian):
    result = {}
    try:
        num = struct.unpack_from(endian + "H", data, offset)[0]
        offset += 2

        for _ in range(num):
            tag, ttype, count = struct.unpack_from(endian + "HHI", data, offset)
            raw4 = data[offset + 8: offset + 12]
            offset += 12

            unit = TIFF_TYPES.get(ttype, (1,))[0]
            total = unit * count

            if total <= 4:
                val = _read_value(raw4 + b"\x00" * 4, 0, ttype, count, endian)
                ptr = None
            else:
                ptr = struct.unpack_from(endian + "I", raw4)[0]
                val = _read_value(data, ptr, ttype, count, endian)

            result[tag] = (val, ptr)
    except Exception:
        pass

    return result


def _valor_racional(v):
    try:
        if isinstance(v, (list, tuple)) and len(v) == 2:
            n, d = v
            return n / d if d else 0.0
        return float(v)
    except Exception:
        return 0.0


def _rational_para_decimal(rationals, ref):
    try:
        dec = (
            _valor_racional(rationals[0]) +
            _valor_racional(rationals[1]) / 60.0 +
            _valor_racional(rationals[2]) / 3600.0
        )
        if str(ref).upper() in ("S", "W"):
            dec = -dec
        return dec
    except Exception:
        return None
    
    
def _rational_para_float(valor):
    try:
        if isinstance(valor, (list, tuple)) and len(valor) == 2:
            n, d = valor
            return n / d if d else None
        return float(valor)
    except Exception:
        return None
    


def _ler_exif_jpeg(caminho):
    try:
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(caminho)
        raw = img._getexif()
        if not raw:
            return None, None, None, None, None

        dados = {TAGS.get(k, k): v for k, v in raw.items()}
        gps_raw = dados.get("GPSInfo")
        dt_str = dados.get("DateTimeOriginal") or dados.get("DateTime")

        lat = lon = altitude = None
        if gps_raw:
            gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}

            if "GPSLatitude" in gps:
                lat = _rational_para_decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
            if "GPSLongitude" in gps:
                lon = _rational_para_decimal(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))

            if "GPSAltitude" in gps:
                altitude = _rational_para_float(gps["GPSAltitude"])
                if altitude is not None and gps.get("GPSAltitudeRef", 0) == 1:
                    altitude = -altitude

        data_fmt = hora_fmt = None
        if dt_str:
            try:
                dt = datetime.strptime(str(dt_str).strip(), "%Y:%m:%d %H:%M:%S")
                data_fmt = dt.strftime("%d/%m/%Y")
                hora_fmt = dt.strftime("%H:%M:%S")
            except Exception:
                pass

        return lat, lon, altitude, data_fmt, hora_fmt

    except Exception:
        return None, None, None, None, None, None


def ler_exif_tiff(caminho):
    try:
        with open(caminho, "rb") as f:
            header = f.read(8)

        if header[:2] == b"II":
            endian = "<"
        elif header[:2] == b"MM":
            endian = ">"
        else:
            return _ler_exif_jpeg(caminho)

        magic = struct.unpack_from(endian + "H", header, 2)[0]
        if magic != 42:
            return None, None, None, None, None

        with open(caminho, "rb") as f:
            data = f.read()

        ifd0_off = struct.unpack_from(endian + "I", data, 4)[0]
        ifd0 = _parse_ifd(data, ifd0_off, endian)

        gps_off = exif_off = None
        dt_str = None

        for tag, (val, ptr) in ifd0.items():
            if tag == 0x8825:
                gps_off = ptr or (val if isinstance(val, int) else None)
            elif tag == 0x8769:
                exif_off = ptr or (val if isinstance(val, int) else None)
            elif tag == 0x0132 and isinstance(val, str):
                dt_str = val

        if exif_off:
            exif_ifd = _parse_ifd(data, exif_off, endian)
            for tag, (val, _) in exif_ifd.items():
                if tag == 0x9003 and isinstance(val, str):
                    dt_str = val

        lat = lon = altitude = None
        if gps_off:
            gps = _parse_ifd(data, gps_off, endian)

            lat_raw = gps.get(2, (None,))[0]
            lat_ref = gps.get(1, (None,))[0]
            lon_raw = gps.get(4, (None,))[0]
            lon_ref = gps.get(3, (None,))[0]
            alt_raw = gps.get(6, (None,))[0]
            alt_ref = gps.get(5, (0,))[0]

            if lat_raw:
                lat = _rational_para_decimal(lat_raw, lat_ref or "N")
            if lon_raw:
                lon = _rational_para_decimal(lon_raw, lon_ref or "E")
            if alt_raw:
                altitude = _rational_para_float(alt_raw)
                if altitude is not None and alt_ref == 1:
                    altitude = -altitude

        data_fmt = hora_fmt = None
        if dt_str:
            try:
                dt = datetime.strptime(str(dt_str).strip(), "%Y:%m:%d %H:%M:%S")
                data_fmt = dt.strftime("%d/%m/%Y")
                hora_fmt = dt.strftime("%H:%M:%S")
            except Exception:
                pass

        return lat, lon, altitude, data_fmt, hora_fmt

    except Exception:
        return None, None, None, None, None


def ler_exif(caminho):
    suf = Path(caminho).suffix.lower()
    if suf in EXTENSOES_DNG or suf in {".tif", ".tiff"}:
        return ler_exif_tiff(caminho)
    return _ler_exif_jpeg(caminho)


# ══════════════════════════════════════════════
# IMAGEM
# ══════════════════════════════════════════════

def abrir_imagem(caminho):
    suf = Path(caminho).suffix.lower()

    if suf in EXTENSOES_DNG:
        try:
            import rawpy
            with rawpy.imread(str(caminho)) as raw:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    half_size=False,
                    no_auto_bright=False,
                    output_bps=8,
                    gamma=(2.222, 4.5),
                )
            img = Image.fromarray(rgb)
        except ImportError:
            raise RuntimeError(
                "rawpy não encontrado. Instale com: pip install rawpy\n"
                "Sem rawpy, o script processa JPG/PNG/TIFF normalmente."
            )
    else:
        img = Image.open(caminho)

    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if APPLY_SHARPEN:
        img = img.filter(
            ImageFilter.UnsharpMask(
                radius=SHARPEN_RADIUS,
                percent=SHARPEN_PERCENT,
                threshold=SHARPEN_THRESHOLD
            )
        )

    return img


def carregar_fonte(tam):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, tam)
        except Exception:
            pass
    return ImageFont.load_default()


def formatar_coord(decimal, tipo):
    if decimal is None:
        return "N/A"

    direcao = ("N" if decimal >= 0 else "S") if tipo == "lat" else ("E" if decimal >= 0 else "W")
    v = abs(decimal)

    graus = int(v)
    minutos_float = (v - graus) * 60
    minutos = int(minutos_float)
    segundos = round((minutos_float - minutos) * 60)

    if segundos == 60:
        segundos = 0
        minutos += 1
    if minutos == 60:
        minutos = 0
        graus += 1

    return f"{graus}°{minutos:02d}'{segundos:02d}\" {direcao}"

def formatar_altitude(altitude):
    if altitude is None:
        return "N/A"
    return f"{altitude:.1f} m"


def medir_texto(draw, texto, fonte):
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def ajustar_fonte_que_caiba(draw, texto, largura_max, tam_inicial, tam_min=10):
    tam = tam_inicial
    while tam >= tam_min:
        fonte = carregar_fonte(tam)
        largura, _ = medir_texto(draw, texto, fonte)
        if largura <= largura_max:
            return fonte
        tam -= 1
    return carregar_fonte(tam_min)


def adicionar_barra(img, lat, lon, altitude, data_fmt, hora_fmt):
    w, h = img.size
    # Aumentei levemente o mínimo para evitar que o texto saia da barra em fotos pequenas
    barra_h = max(180, min(MAX_BAR_HEIGHT, int(h * BAR_HEIGHT_RATIO)))

    resultado = Image.new("RGB", (w, h + barra_h), (0, 0, 0))
    resultado.paste(img.convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(resultado)

   
    # Linha de topo
    draw.line([(0, h), (w, h)], fill=LABEL_COLOR, width=max(8, barra_h // 20))

    col_w = w // 4
    pad_x = max(35, int(col_w * 0.12))
    
    rotulos = ["LATITUDE", "LONGITUDE", "ALTITUDE", "DATA / HORA"]
    valor_1 = [formatar_coord(lat, "lat"), formatar_coord(lon, "lon"), formatar_altitude(altitude), data_fmt or "—"]
    valor_2 = ["", "", "", hora_fmt or "—"]

    largura_util = col_w - (pad_x * 2)

    # Fontes Base
    fonte_rotulo_base = max(25, barra_h // 5)
    fonte_valor_base = max(35, barra_h // 2.5) 

    for i in range(4):
        x0 = i * col_w + pad_x
        y_cursor = h + (barra_h * 0.15)

        # --- AJUSTE DE TAMANHO PARA DATA/HORA ---
        # Se for a última coluna (índice 3), reduzimos a fonte em 25% para caber melhor
        if i == 3:
            f_val_mult = 0.75  
            f_rot_mult = 0.90
        else:
            f_val_mult = 1.0
            f_rot_mult = 1.0

        # 1. Desenhar Rótulo
        f_rot = ajustar_fonte_que_caiba(draw, rotulos[i], largura_util, int(fonte_rotulo_base * f_rot_mult), tam_min=20)
        draw.text((x0, y_cursor), rotulos[i], font=f_rot, fill=LABEL_COLOR)
        
        _, h_rot = medir_texto(draw, rotulos[i], f_rot)
        y_cursor += h_rot + (barra_h * 0.03)

        # 2. Desenhar Valor Principal (Data ou Coordenada)
        f_val1 = ajustar_fonte_que_caiba(draw, valor_1[i], largura_util, int(fonte_valor_base * f_val_mult), tam_min=22)
        draw.text((x0, y_cursor), valor_1[i], font=f_val1, fill=TEXT_COLOR)
        
        # 3. Desenhar Valor Secundário (Hora)
        if valor_2[i]:
            _, h_v1 = medir_texto(draw, valor_1[i], f_val1)
            y_cursor += h_v1 + 2 # Espaço curto entre data e hora
            # A hora fica levemente menor que a data para criar hierarquia
            f_val2 = ajustar_fonte_que_caiba(draw, valor_2[i], largura_util, int(fonte_valor_base * f_val_mult * 0.9), tam_min=20)
            draw.text((x0, y_cursor), valor_2[i], font=f_val2, fill=TEXT_COLOR)

        # Divisórias
        if i > 0:
            draw.line([(i * col_w, h + (barra_h * 0.25)), (i * col_w, h + (barra_h * 0.75))], fill=(100,100,100), width=4)

    return resultado
# ══════════════════════════════════════════════
# PROCESSAMENTO
# ══════════════════════════════════════════════

def salvar_resultado(img, saida):
    ext = saida.suffix.lower()
    if ext == ".png":
        img.save(str(saida), compress_level=PNG_COMPRESS_LEVEL)
    else:
        img.save(str(saida), quality=JPEG_QUALITY, subsampling=0, optimize=True)


def processar_arquivo(caminho_in, pasta_out):
    lat, lon, altitude, data_fmt, hora_fmt = ler_exif(caminho_in)

    if lat is None and lon is None and altitude is None and not data_fmt and not hora_fmt:
        return "sem_metadados", None

    img = abrir_imagem(caminho_in)
    resultado = adicionar_barra(img, lat, lon, altitude, data_fmt, hora_fmt)

    saida = pasta_out / f"{Path(caminho_in).stem}_com_barra.jpg"
    salvar_resultado(resultado, saida)

    return "ok", saida


def listar_imagens(pasta_in):
    return sorted(
        f for f in pasta_in.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSOES
    )


def main():
    pasta_in = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    pasta_out = Path(sys.argv[2]) if len(sys.argv) > 2 else pasta_in / "saida_com_barra"

    if not pasta_in.exists():
        print(f"[ERRO] Pasta não encontrada: {pasta_in}")
        sys.exit(1)

    pasta_out.mkdir(parents=True, exist_ok=True)
    fotos = listar_imagens(pasta_in)

    if not fotos:
        print(f"Nenhuma imagem encontrada em: {pasta_in.resolve()}")
        sys.exit(0)

    print("─" * 64)
    print(f"Entrada : {pasta_in.resolve()}")
    print(f"Saída   : {pasta_out.resolve()}")
    print(f"Fotos   : {len(fotos)}")
    print("─" * 64)

    ok = 0
    sem_meta = 0
    erros = 0

    for foto in fotos:
        try:
            status, saida = processar_arquivo(foto, pasta_out)
            if status == "ok":
                ok += 1
                print(f"[OK ] {foto.name} -> {saida.name}")
            else:
                sem_meta += 1
                print(f"[SKIP] {foto.name} (sem GPS/data EXIF)")
        except RuntimeError as e:
            erros += 1
            print(f"[ERRO] {foto.name} -> {e}")
        except Exception as e:
            erros += 1
            print(f"[ERRO] {foto.name} -> {e}")

    print("─" * 64)
    print(f"Processadas        : {ok}")
    print(f"Sem metadados úteis: {sem_meta}")
    print(f"Erros              : {erros}")
    print("─" * 64)

'''
if __name__ == "__main__":
    main()
'''

from pathlib import Path

# --- DEFINA AQUI SEUS CAMINHOS ---
pasta_entrada = r"C:/Users/tiagobatista/Downloads/TesteFotos"  # Use 'r' antes das aspas para evitar erros de barra
pasta_saida = r"C:/Users/tiagobatista/Downloads/TesteFotos/saida_com_barra"

# --- LÓGICA DE EXECUÇÃO ---
path_in = Path(pasta_entrada)
path_out = Path(pasta_saida)

if not path_in.exists():
    print(f"[ERRO] Pasta não encontrada: {path_in}")
else:
    path_out.mkdir(parents=True, exist_ok=True)
    fotos = listar_imagens(path_in)

    if not fotos:
        print(f"Nenhuma imagem encontrada em: {path_in.resolve()}")
    else:
        print(f"Processando {len(fotos)} fotos...")
        ok, sem_meta, erros = 0, 0, 0

        for foto in fotos:
            try:
                status, saida = processar_arquivo(foto, path_out)
                if status == "ok":
                    ok += 1
                    print(f"[OK ] {foto.name}")
                else:
                    sem_meta += 1
                    print(f"[SKIP] {foto.name} (sem metadados)")
            except Exception as e:
                erros += 1
                print(f"[ERRO] {foto.name}: {e}")

        print("-" * 30)
        print(f"Concluído! Sucesso: {ok} | Sem Metadados: {sem_meta} | Erros: {erros}")
