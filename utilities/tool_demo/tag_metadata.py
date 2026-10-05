"""Encode a PNG frame sequence to an animated AVIF with embedded XMP + EXIF (title, description, creator,
rights, license, alt text), ported from the Joteo tool-demo pipeline. The site is run by an individual, so the
creator is the author's name and there is no company address or phone."""
import json
import subprocess
import uuid
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

import piexif

ROOT = Path(__file__).resolve().parents[2]
SITE = json.loads((ROOT / "src/config/site.json").read_text(encoding="utf-8"))
AUTHOR = json.loads((ROOT / "src/config/author.json").read_text(encoding="utf-8"))
BASE = SITE["base_url"]
SITE_NAME = SITE["site_name"]
CREATOR = AUTHOR["name"]
CREATOR_TOOL = f"{SITE_NAME} demo recorder 1.0"
LICENSE_URL = f"{BASE}/terms.html"
USAGE_TERMS = f"This demo may be shared with a link back to {BASE}/. All other rights reserved."

FPS = 15
QCOLOR = 45
SPEED = 6


def build_alt_text(name, labels, result_label):
    fields = ", ".join(labels) if labels else "the inputs"
    return f"Animated walkthrough of the {name}: entering {fields}, then reading the {result_label}."


def build_xmp(tool, alt_text, width, height, duration_s):
    page_url = f"{BASE}/{tool['slug']}.html"
    today, year = date.today().isoformat(), date.today().year
    rights = f"© {year} {SITE_NAME} — All rights reserved"
    title = escape(tool["meta_title"] or tool["h1"])
    description = escape(tool["meta_description"])
    e = escape
    xmp = (
        "<?xpacket begin='﻿' id='W5M0MpCehiHzreSzNTczkc9d'?>\n<x:xmpmeta xmlns:x='adobe:ns:meta/'>\n"
        "  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>\n    <rdf:Description rdf:about=''\n"
        "      xmlns:dc='http://purl.org/dc/elements/1.1/' xmlns:xmp='http://ns.adobe.com/xap/1.0/'\n"
        "      xmlns:xmpRights='http://ns.adobe.com/xap/1.0/rights/' xmlns:xmpMM='http://ns.adobe.com/xap/1.0/mm/'\n"
        "      xmlns:xmpDM='http://ns.adobe.com/xmp/1.0/DynamicMedia/' xmlns:photoshop='http://ns.adobe.com/photoshop/1.0/'\n"
        "      xmlns:Iptc4xmpCore='http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/'\n"
        "      xmlns:Iptc4xmpExt='http://iptc.org/std/Iptc4xmpExt/2008-02-29/' xmlns:plus='http://ns.useplus.org/ldf/xmp/1.0/'>\n"
        f"      <dc:title><rdf:Alt><rdf:li xml:lang='x-default'>{title}</rdf:li></rdf:Alt></dc:title>\n"
        f"      <dc:description><rdf:Alt><rdf:li xml:lang='x-default'>{description}</rdf:li></rdf:Alt></dc:description>\n"
        f"      <dc:subject><rdf:Bag><rdf:li>{e(tool['name'])}</rdf:li><rdf:li>walkthrough</rdf:li></rdf:Bag></dc:subject>\n"
        f"      <dc:rights><rdf:Alt><rdf:li xml:lang='x-default'>{e(rights)}</rdf:li></rdf:Alt></dc:rights>\n"
        f"      <dc:creator><rdf:Seq><rdf:li>{e(CREATOR)}</rdf:li></rdf:Seq></dc:creator>\n"
        f"      <dc:publisher><rdf:Bag><rdf:li>{e(SITE_NAME)}</rdf:li></rdf:Bag></dc:publisher>\n"
        f"      <dc:source>{page_url}</dc:source>\n      <dc:identifier>{page_url}</dc:identifier>\n"
        f"      <dc:relation><rdf:Bag><rdf:li>{page_url}</rdf:li></rdf:Bag></dc:relation>\n      <xmp:BaseURL>{page_url}</xmp:BaseURL>\n      <dc:format>image/avif</dc:format>\n      <dc:type>MovingImage</dc:type>\n"
        "      <dc:language><rdf:Bag><rdf:li>en</rdf:li></rdf:Bag></dc:language>\n"
        f"      <xmpMM:DocumentID>uuid:{uuid.uuid5(uuid.NAMESPACE_URL, page_url)}</xmpMM:DocumentID>\n"
        f"      <xmpMM:InstanceID>uuid:{uuid.uuid4()}</xmpMM:InstanceID>\n"
        f"      <xmp:CreateDate>{today}</xmp:CreateDate>\n      <xmp:ModifyDate>{today}</xmp:ModifyDate>\n"
        f"      <xmp:CreatorTool>{e(CREATOR_TOOL)}</xmp:CreatorTool>\n"
        f"      <xmpRights:WebStatement>{LICENSE_URL}</xmpRights:WebStatement>\n      <xmpRights:Marked>True</xmpRights:Marked>\n"
        f"      <xmpRights:UsageTerms><rdf:Alt><rdf:li xml:lang='x-default'>{e(USAGE_TERMS)}</rdf:li></rdf:Alt></xmpRights:UsageTerms>\n"
        f"      <xmpDM:duration rdf:parseType='Resource'><xmpDM:value>{duration_s:.3f}</xmpDM:value><xmpDM:scale>1/1</xmpDM:scale></xmpDM:duration>\n"
        f"      <xmpDM:videoFrameRate>{FPS}</xmpDM:videoFrameRate>\n"
        f"      <photoshop:Credit>{e(SITE_NAME)}</photoshop:Credit>\n      <photoshop:Source>{page_url}</photoshop:Source>\n"
        f"      <photoshop:Headline>{title}</photoshop:Headline>\n"
        f"      <Iptc4xmpCore:CopyrightNotice>{e(rights)}</Iptc4xmpCore:CopyrightNotice>\n"
        f"      <Iptc4xmpCore:CreatorContactInfo><rdf:Description><Iptc4xmpCore:CiUrlWork>{page_url}</Iptc4xmpCore:CiUrlWork></rdf:Description></Iptc4xmpCore:CreatorContactInfo>\n"
        f"      <Iptc4xmpCore:AltTextAccessibility><rdf:Alt><rdf:li xml:lang='x-default'>{e(alt_text)}</rdf:li></rdf:Alt></Iptc4xmpCore:AltTextAccessibility>\n"
        f"      <Iptc4xmpCore:ExtDescrAccessibility><rdf:Alt><rdf:li xml:lang='x-default'>{description}</rdf:li></rdf:Alt></Iptc4xmpCore:ExtDescrAccessibility>\n"
        f"      <plus:LicensorURL><rdf:Bag><rdf:li>{LICENSE_URL}</rdf:li></rdf:Bag></plus:LicensorURL>\n"
        "      <Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/screenCapture</Iptc4xmpExt:DigitalSourceType>\n"
        f"      <Iptc4xmpExt:MaxAvailWidth>{width}</Iptc4xmpExt:MaxAvailWidth>\n      <Iptc4xmpExt:MaxAvailHeight>{height}</Iptc4xmpExt:MaxAvailHeight>\n"
        "    </rdf:Description>\n  </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end='w'?>")
    return xmp.encode("utf-8")


def build_exif(tool, width, height):
    """EXIF strings are ASCII, so © and em dashes are substituted here (the XMP copy keeps the real characters)."""
    now = date.today().strftime("%Y:%m:%d 00:00:00").encode()
    asc = lambda s: s.replace("©", "(c)").replace("—", "-").encode("ascii", "replace")
    page_url = f"{BASE}/{tool['slug']}.html"
    zeroth = {piexif.ImageIFD.DocumentName: asc(tool["meta_title"] or tool["h1"]),
              piexif.ImageIFD.ImageDescription: asc(f"{tool['meta_description']} Tool page: {page_url}"),
              piexif.ImageIFD.Copyright: asc(f"© {date.today().year} {SITE_NAME} — All rights reserved"),
              piexif.ImageIFD.Artist: asc(CREATOR), piexif.ImageIFD.Software: asc(CREATOR_TOOL),
              piexif.ImageIFD.DateTime: now}
    exif = {piexif.ExifIFD.UserComment: b"ASCII\x00\x00\x00" + asc(f"Source page: {page_url}"),
            piexif.ExifIFD.DateTimeOriginal: now, piexif.ExifIFD.DateTimeDigitized: now,
            piexif.ExifIFD.PixelXDimension: width, piexif.ExifIFD.PixelYDimension: height}
    return piexif.dump({"0th": zeroth, "Exif": exif, "GPS": {}, "1st": {}, "thumbnail": None})


def encode_tagged_avif(tool, alt_text, frames_dir, out_path, width, height, n_frames, qcolor=QCOLOR):
    xmp, exif = frames_dir.parent / "metadata.xmp", frames_dir.parent / "metadata.exif"
    xmp.write_bytes(build_xmp(tool, alt_text, width, height, n_frames / FPS))
    exif.write_bytes(build_exif(tool, width, height))
    frames = sorted(frames_dir.glob("frame_*.png"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["avifenc", "--fps", str(FPS), "-k", "0", "-q", str(qcolor), "--speed", str(SPEED), "--jobs", "2",
                    "--repetition-count", "infinite", "--xmp", str(xmp), "--exif", str(exif),
                    *map(str, frames), str(out_path)], check=True, capture_output=True)
