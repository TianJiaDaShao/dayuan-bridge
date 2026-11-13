#!/usr/bin/python3
"""Reproducible local package build; does not install or load services."""
import hashlib,json,os,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BUILD=Path(os.environ.get('DAYUAN_BUILD_DIR',str(ROOT/'.build')))
VERSION='0.2.5'
DIST=ROOT/'site/dist/downloads'

def run(args):subprocess.run([str(x) for x in args],check=True,env=dict(os.environ,COPYFILE_DISABLE='1'))
def main():
 if BUILD.exists():shutil.rmtree(BUILD)
 payload=BUILD/'payload';prefix=payload/'Library/Application Support/Dayuan Bridge'
 prefix.parent.mkdir(parents=True,exist_ok=True)
 shutil.copytree(ROOT/'service/runtime',prefix,ignore=shutil.ignore_patterns('__pycache__'),copy_function=shutil.copyfile)
 daemon=payload/'Library/LaunchDaemons';daemon.mkdir(parents=True)
 shutil.copyfile(ROOT/'service/local.dayuan.bridge.plist',daemon/'local.dayuan.bridge.plist')
 bindir=payload/'usr/local/bin';bindir.mkdir(parents=True);(bindir/'dayuan').symlink_to('/Library/Application Support/Dayuan Bridge/dayuan-cli')
 for path in payload.rglob('*'):
  if path.is_symlink():continue
  path.chmod(0o755 if path.is_dir() or path.name=='dayuan-cli' else 0o644)
 scripts=BUILD/'scripts';shutil.copytree(ROOT/'service/installer-scripts',scripts,ignore=shutil.ignore_patterns('__pycache__'))
 for path in scripts.iterdir():path.chmod(0o755 if path.name in ('preinstall','postinstall') else 0o644)
 component=BUILD/'DayuanBridge-component.pkg'
 run(['/usr/bin/pkgbuild','--root',payload,'--scripts',scripts,'--identifier','local.dayuan.bridge','--version',VERSION,'--install-location','/','--ownership','recommended',component])
 distribution=BUILD/'Distribution.xml'
 distribution.write_text('''<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
<title>圆桥 Dayuan Bridge</title>
<organization>local.dayuan</organization>
<domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
<options customize="never" require-scripts="true" hostArchitectures="arm64" rootVolumeOnly="true"/>
<welcome file="welcome.html" mime-type="text/html"/><conclusion file="conclusion.html" mime-type="text/html"/>
<choices-outline><line choice="default"><line choice="local.dayuan.bridge"/></line></choices-outline>
<choice id="default"/><choice id="local.dayuan.bridge" visible="false"><pkg-ref id="local.dayuan.bridge"/></choice>
<pkg-ref id="local.dayuan.bridge" version="0.2.5" onConclusion="none">DayuanBridge-component.pkg</pkg-ref>
</installer-gui-script>''',encoding='utf-8')
 DIST.mkdir(parents=True,exist_ok=True);package=DIST/('DayuanBridge-'+VERSION+'.pkg')
 run(['/usr/bin/productbuild','--distribution',distribution,'--resources',ROOT/'service/resources','--package-path',BUILD,package])
 source=DIST/('DayuanBridge-'+VERSION+'-source.zip')
 with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as archive:
  for path in (ROOT/'service').rglob('*'):
   if path.is_file() and '__pycache__' not in path.parts and path.name!='native_fixture' and not any(part.endswith('.dSYM') for part in path.parts):archive.write(path,Path('DayuanBridge')/path.relative_to(ROOT))
  archive.write(Path(__file__),Path('DayuanBridge/build_package.py'))
  for path in [ROOT/'README.md',ROOT/'.gitignore',*(ROOT/'docs').glob('*.md')]:
   if path.is_file():archive.write(path,Path('DayuanBridge')/path.relative_to(ROOT))
  for path in (ROOT/'site/dist').glob('*'):
   if path.is_file():archive.write(path,Path('DayuanBridge/site/dist')/path.name)
 hashes=[]
 for path in [package,source]:hashes.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
 (DIST/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n')
 print('BUILD_COMPLETE',package)
if __name__=='__main__':main()
