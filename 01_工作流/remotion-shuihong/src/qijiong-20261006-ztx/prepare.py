from pathlib import Path
import json,math,hashlib,shutil
from PIL import Image, ImageEnhance
ROOT=Path('D:/history/codx_3 history studio')
OUT=ROOT/'05_项目/Remotion/REMOTION-QIJIONG-ZTX-20261006/QJ-ZTX-A1'
WB=ROOT/'05_项目/Remotion/REMOTION-QIJIONG-WB-20261006/QJ-WB-A1'
HERE=Path(__file__).parent
OUT.mkdir(parents=True,exist_ok=False)
for folder in ['assets','source','qa','reference']:(OUT/folder).mkdir()
for n in ['mix.wav','narration.wav','original-bed.wav','jiong.png','Sans.ttf','Serif.ttf','OFL.txt','rivers.geojson']:
 shutil.copy2(WB/'assets'/n,OUT/'assets'/n)
scene=json.loads((WB/'source/scene.json').read_text(encoding='utf-8'))
scene.pop('jin',None);scene['build_id']='QJ-ZTX-A1'
scene['camera']=[dict(t=t,z=z,cx=x,cy=y) for t,z,x,y in [(0,.65,1040,550),(4.16,.7,1150,510),(8.64,2.5,1370,470),(12.04,2.65,1370,470),(15.88,2.7,1370,475),(18.4,2.6,1210,360),(20.7,2.2,1200,350),(24.6,.7,1040,550),(26,.65,1040,550)]]
scene['raster']=dict(x=-700,y=-650,width=3600,height=2400,center=[111.5,34],scale=12000)
tile_records=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def layer(z,dirs):
 files={}
 for d in dirs:
  for p in (ROOT/'.workbuddy'/d).glob(f'relief_{z}_*.jpg'):
   _,_,x,y=p.stem.split('_');files[(int(x),int(y))]=p
 xs=[p[0] for p in files];ys=[p[1] for p in files]
 x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
 im=Image.new('RGBA',((x1-x0+1)*256,(y1-y0+1)*256))
 for (x,y),p in files.items():
  im.paste(Image.open(p).convert('RGBA'),((x-x0)*256,(y-y0)*256))
  tile_records.append(dict(path=str(p),sha256=sha(p),z=z,x=x,y=y))
 n=256*2**z;k=n/(2*math.pi*12000)
 m=math.log(math.tan(math.pi/4+math.radians(34)/2))
 # Input tile pixels = affine transform of target Mercator pixels.
 tx=n*(111.5+180)/360+k*(-700-960)-x0*256
 ty=n*(math.pi-m)/(2*math.pi)+k*(-650-540)-y0*256
 return im.transform((3600,2400),Image.Transform.AFFINE,(k,0,tx,0,k,ty),Image.Resampling.BICUBIC)
base=layer(8,['basemap_z8_cache','wide2_cache'])
high=layer(9,['relief_z9_v2_cache','relief_z9_core_cache'])
base=Image.alpha_composite(base,high)
missing=sum(1 for a in base.getchannel('A').getdata() if a<255)
rgb=ImageEnhance.Color(base.convert('RGB')).enhance(.28)
rgb=ImageEnhance.Contrast(rgb).enhance(1.1)
rgb=Image.blend(rgb,Image.new('RGB',rgb.size,'#d8bda0'),.22)
rgb.save(OUT/'assets/relief.png')
(OUT/'map-provenance.json').write_text(json.dumps(dict(source='Existing local Esri World_Shaded_Relief cached z8/z9 tiles; no new downloads',source_url='https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer',attribution='Esri, USGS, NOAA',rights='Copyright Esri; attribution provided. Local review sample only; commercial/public redistribution not cleared.',projection=scene['raster'],uncovered_pixels=missing,tiles=tile_records,hydrology='Frozen Natural Earth 1:50m modern river GeoJSON, public domain; not an ancient channel reconstruction',jin_polygon_used=False),ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared',OUT,'uncovered full-raster pixels',missing)
