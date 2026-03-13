"""
SISTEMA DE PROCESSAMENTO E ESTAMPAGEM DE METADADOS GEOGRÁFICOS (v2.0)
-------------------------------------------------------------------
Descrição:
    Este script automatiza a leitura de metadados EXIF (GPS) de imagens (JPG/PNG/DNG)
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
    - padronização das imagens para inserção em documentos 

Requisitos:
    - Pillow (PIL), Matplotlib (para previews), Pathlib.

Autor: Tiago Alexandre Batista - DUDJUINA/SEMA
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
        return None, None, None, None, None


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

def normalizar_texto_exibicao(lat, lon, altitude, data_fmt, hora_fmt):
    return {
        "LATITUDE":  formatar_coord(lat, "lat"),
        "LONGITUDE": formatar_coord(lon, "lon"),
        "ALTITUDE":  formatar_altitude(altitude),
        "DATA":      data_fmt.strip() if data_fmt else "—",
        "HORA":      hora_fmt.strip() if hora_fmt else "—",
    }

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

    MAX_LARGURA = 2000
    if img.width > MAX_LARGURA:
        proporcao = MAX_LARGURA / float(img.width)
        nova_altura = int(float(img.height) * float(proporcao))
        img = img.resize((MAX_LARGURA, nova_altura), Image.Resampling.LANCZOS)

    w, h = img.size
    barra_h = max(180, min(MAX_BAR_HEIGHT, int(h * BAR_HEIGHT_RATIO)))

    resultado = Image.new("RGB", (w, h + barra_h), BAR_BG_COLOR)
    resultado.paste(img.convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(resultado)

    # Linha superior
    draw.line([(0, h), (w, h)], fill=LABEL_COLOR, width=max(8, barra_h // 20))

    col_w = w // 4
    margem_interna = max(20, int(col_w * 0.08))
    largura_util = col_w - (margem_interna * 2)

    rotulos = ["LATITUDE", "LONGITUDE", "ALTITUDE", "DATA / HORA"]
    valor_1 = [
        formatar_coord(lat, "lat"),
        formatar_coord(lon, "lon"),
        formatar_altitude(altitude),
        data_fmt or "—"
    ]
    valor_2 = ["", "", "", hora_fmt or "—"]

    fonte_rotulo_base = max(22, barra_h // 5)
    fonte_valor_base = max(34, int(barra_h * 0.30))

    for i in range(4):
        x_col_ini = i * col_w
        x_col_centro = x_col_ini + (col_w / 2)

        # Hierarquia visual
        if i in (0, 1):  # latitude / longitude
            rot_mult = 1.00
            val1_mult = 1.18
            val2_mult = 1.00
        elif i == 2:     # altitude
            rot_mult = 0.92
            val1_mult = 0.88
            val2_mult = 0.90
        else:            # data / hora
            rot_mult = 0.95
            val1_mult = 1.10
            val2_mult = 0.90

        # Fontes ajustadas
        f_rot = ajustar_fonte_que_caiba(
            draw, rotulos[i], largura_util,
            int(fonte_rotulo_base * rot_mult), tam_min=18
        )
        f_val1 = ajustar_fonte_que_caiba(
            draw, valor_1[i], largura_util,
            int(fonte_valor_base * val1_mult), tam_min=22
        )

        if valor_2[i]:
            f_val2 = ajustar_fonte_que_caiba(
                draw, valor_2[i], largura_util,
                int(fonte_valor_base * val2_mult), tam_min=18
            )
        else:
            f_val2 = None

        # Medidas dos textos
        w_rot, h_rot = medir_texto(draw, rotulos[i], f_rot)
        w_v1, h_v1 = medir_texto(draw, valor_1[i], f_val1)

        gap_rot_val = int(barra_h * 0.045)
        gap_val1_val2 = int(barra_h * 0.035) if f_val2 else 0

        if f_val2:
            w_v2, h_v2 = medir_texto(draw, valor_2[i], f_val2)
            altura_bloco = h_rot + gap_rot_val + h_v1 + gap_val1_val2 + h_v2
        else:
            w_v2, h_v2 = 0, 0
            altura_bloco = h_rot + gap_rot_val + h_v1

        # Centralização vertical do bloco inteiro dentro da barra
        y_inicio = h + int((barra_h - altura_bloco) / 2)

        # Centralização horizontal por linha
        x_rot = int(x_col_centro - (w_rot / 2))
        x_v1 = int(x_col_centro - (w_v1 / 2))
        x_v2 = int(x_col_centro - (w_v2 / 2)) if f_val2 else 0

        # Segurança para não encostar nas bordas internas da coluna
        x_min = x_col_ini + margem_interna
        x_max_rot = x_col_ini + col_w - margem_interna - w_rot
        x_max_v1 = x_col_ini + col_w - margem_interna - w_v1
        x_max_v2 = x_col_ini + col_w - margem_interna - w_v2 if f_val2 else 0

        x_rot = max(x_min, min(x_rot, x_max_rot))
        x_v1 = max(x_min, min(x_v1, x_max_v1))
        if f_val2:
            x_v2 = max(x_min, min(x_v2, x_max_v2))

        # Desenho
        y_rot = y_inicio
        y_v1 = y_rot + h_rot + gap_rot_val

        draw.text((x_rot, y_rot), rotulos[i], font=f_rot, fill=LABEL_COLOR)
        draw.text((x_v1, y_v1), valor_1[i], font=f_val1, fill=TEXT_COLOR)

        if f_val2:
            y_v2 = y_v1 + h_v1 + gap_val1_val2
            draw.text((x_v2, y_v2), valor_2[i], font=f_val2, fill=TEXT_COLOR)

        # Divisórias
        if i > 0:
            x_div = i * col_w
            draw.line(
                [(x_div, h + int(barra_h * 0.24)), (x_div, h + int(barra_h * 0.78))],
                fill=(100, 100, 100),
                width=3
            )

    return resultado
# ══════════════════════════════════════════════
# PROCESSAMENTO
# ══════════════════════════════════════════════

def redimensionar_e_padronizar(img):
    """
    Padroniza a resolução para relatórios e garante que a imagem esteja em RGB.
    """
    # 1. Garante que a imagem está no modo de cor correto (evita erro em PNG/HEIC)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 2. Define um teto de resolução (2000px é o ideal para PDFs técnicos)
    MAX_RES = 2000
    w, h = img.size
    
    if w > MAX_RES or h > MAX_RES:
        if w > h:
            nova_largura = MAX_RES
            nova_altura = int((h * MAX_RES) / w)
        else:
            nova_altura = MAX_RES
            nova_largura = int((w * MAX_RES) / h)
        
        # Uso do Resampling.LANCZOS para manter a nitidez dos detalhes ambientais
        img = img.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)
    
    return img

def salvar_resultado(img, saida):
    """
    Salva em JPEG otimizado, forçando a extensão correta.
    """
    caminho_jpg = saida.with_suffix(".jpg")

    # Se a imagem tiver canal Alpha (transparência), precisamos converter para RGB,
    # caso contrário o JPEG dará erro.
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    img.save(
        str(caminho_jpg),
        "JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True
    )
    return caminho_jpg


def processar_arquivo(caminho_in, pasta_out):
    lat, lon, altitude, data_fmt, hora_fmt = ler_exif(caminho_in)

    # Fallback: usa a data de modificação do arquivo quando não houver data EXIF
    if not data_fmt:
        ts = os.path.getmtime(caminho_in)
        dt = datetime.fromtimestamp(ts)
        data_fmt = dt.strftime("%d/%m/%Y")
        hora_fmt = dt.strftime("%H:%M:%S")

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


if __name__ == "__main__":

    print("─" * 60)
    print("PROCESSADOR DE METADADOS GEOGRÁFICOS DE IMAGENS")
    print("─" * 60)

    pasta_entrada = input("Informe o caminho da pasta com as fotos: ").strip()

    if not pasta_entrada:
        print("Nenhuma pasta informada. Encerrando.")
        sys.exit(1)

    path_in = Path(pasta_entrada)

    if not path_in.exists():
        print(f"[ERRO] Pasta não encontrada: {path_in}")
        sys.exit(1)

    path_out = path_in / "saida_com_barra"
    path_out.mkdir(parents=True, exist_ok=True)

    fotos = listar_imagens(path_in)

    if not fotos:
        print(f"Nenhuma imagem encontrada em: {path_in.resolve()}")
        sys.exit(0)

    print("─" * 60)
    print(f"Pasta de entrada : {path_in.resolve()}")
    print(f"Pasta de saída   : {path_out.resolve()}")
    print(f"Fotos encontradas: {len(fotos)}")
    print("─" * 60)

    ok = 0
    sem_meta = 0
    erros = 0

    for foto in fotos:
        try:
            status, saida = processar_arquivo(foto, path_out)

            if status == "ok":
                ok += 1
                print(f"[OK ] {foto.name}")

            else:
                sem_meta += 1
                print(f"[SKIP] {foto.name} (sem metadados EXIF)")

        except Exception as e:
            erros += 1
            print(f"[ERRO] {foto.name}: {e}")

    print("─" * 60)
    print(f"Processadas : {ok}")
    print(f"Sem EXIF    : {sem_meta}")
    print(f"Erros       : {erros}")
    print("─" * 60)
