"""build_vscode_vsix.py -- package integrations/vscode as a .vsix, standard library only.

    python scripts/build_vscode_vsix.py --out dist/flywheel-code-0.1.0.vsix

A .vsix is a zip with an OPC content-types file, an extension.vsixmanifest and
the extension under extension/. This writes exactly the files the extension
needs, in a fixed order with fixed timestamps, so the same source gives the same
bytes. Installing the result needs no build tools: `code --install-extension`.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "integrations" / "vscode"
FILES = ("package.json", "extension.js", "README.md", "LICENSE")
EPOCH = (2020, 1, 1, 0, 0, 0)

CONTENT_TYPES = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension=".json" ContentType="application/json"/>'
                 '<Default Extension=".js" ContentType="application/javascript"/>'
                 '<Default Extension=".md" ContentType="text/markdown"/>'
                 '<Default Extension=".txt" ContentType="text/plain"/>'
                 '<Default Extension=".vsixmanifest" ContentType="text/xml"/></Types>')


def manifest(pkg: dict) -> str:
    cats = ",".join(pkg.get("categories", []))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(pkg['name'])}" Version="{escape(pkg['version'])}" Publisher="{escape(pkg['publisher'])}"/>
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags></Tags>
    <Categories>{escape(cats)}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
      <Property Id="Microsoft.VisualStudio.Services.Links.Source" Value="{escape(pkg['repository']['url'])}"/>
    </Properties>
    <License>extension/LICENSE.txt</License>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true"/>
  </Assets>
</PackageManifest>
"""


def build(out: Path) -> Path:
    pkg = json.loads((SRC / "package.json").read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        def put(name, data):
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
        put("[Content_Types].xml", CONTENT_TYPES)
        put("extension.vsixmanifest", manifest(pkg))
        for name in FILES:
            data = (SRC / name).read_bytes().replace(b"\r\n", b"\n")
            put("extension/" + ("LICENSE.txt" if name == "LICENSE" else name), data)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    pkg = json.loads((SRC / "package.json").read_text(encoding="utf-8"))
    ap.add_argument("--out", default=str(ROOT / "dist" / f"flywheel-code-{pkg['version']}.vsix"))
    args = ap.parse_args(argv)
    print(build(Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
