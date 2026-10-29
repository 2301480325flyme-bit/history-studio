import React from 'react';
import {AbsoluteFill, Composition, Img, interpolate, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import {CameraRig} from '../Camera';
import {FlagRise, useVerbTiming} from '../ActionLayer';
import data from './scene.json';

const INK='#302c28', RED='#8f372e', GOLD='#b48e4e';
const merc=(lat:number)=>Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
const project=(lon:number,lat:number):[number,number]=>[960+(lon-113.5)*Math.PI/180*13318,540-13318*(merc(lat)-merc(35.1))];
const place=(id:string)=>data.places.find(p=>p.id===id)!;
const yang=place('yangzhai_approx'), luo=place('luoyang_han_wei'), xu=place('xuchang_approx');
const [yx,yy]=project(yang.coordinates[0],yang.coordinates[1]);
const [lx,ly]=project(luo.coordinates[0],luo.coordinates[1]);
const clamp=(n:number)=>Math.max(0,Math.min(1,n));
// Imported flag geometry uses legacy core projection. Affine correction converts
// its geographic anchors to the generator projection without editing old modules.
const a=13318/13500;
const legacyToCore=`translate(${960*(1-a)} ${540*(1-a)+13318*(merc(35.1)-merc(35.2))}) scale(${a})`;

const City:React.FC<{record:typeof yang;label:string;detail:string;opacity?:number;active?:boolean}>=({record,label,detail,opacity=1,active=false})=>{
 const [x,y]=project(record.coordinates[0],record.coordinates[1]);
 return <g transform={`translate(${x} ${y})`} opacity={opacity}>
  <circle r={active?19:12} fill="#f6f1e6" stroke={active?RED:'#746a5d'} strokeWidth={active?2.8:1.8}/>
  <path d="M -6 5 V -4 L 0 -10 L 6 -4 V 5 Z" fill={active?RED:'#746a5d'}/>
  <text x="0" y="41" textAnchor="middle" fill={active?RED:INK} fontSize="25" fontWeight="600" stroke="#f4f0e7" strokeWidth="6" paintOrder="stroke">{label}</text>
  <text x="0" y="62" textAnchor="middle" fill="#746a5d" fontSize="13" stroke="#f4f0e7" strokeWidth="4" paintOrder="stroke">{detail}</text>
 </g>;
};

const Direction:React.FC<{frame:number}>=({frame})=>{
 const start=12*30, end=18*30;
 if(frame<start||frame>=end)return null;
 const op=Math.min(1,(frame-start)/15,(end-frame)/15);
 const p=clamp((frame-start)/(3*30));
 const dx=lx-yx,dy=ly-yy,len=Math.hypot(dx,dy);
 // Stop before the city: a screen-space direction graphic, not a marching route.
 const ex=lx+110,ey=ly+6;
 const cx=(yx+ex)/2+30,cy=(yy+ey)/2-28;
 const tx=(1-p)*(1-p)*yx+2*(1-p)*p*cx+p*p*ex;
 const ty=(1-p)*(1-p)*(yy-20)+2*(1-p)*p*cy+p*p*ey;
 const angle=Math.atan2(2*(1-p)*(cy-(yy-20))+2*p*(ey-cy),2*(1-p)*(cx-yx)+2*p*(ex-cx))*180/Math.PI;
 const d=`M ${yx} ${yy-20} Q ${cx} ${cy} ${tx} ${ty}`;
 return <g opacity={op}>
  <path d={d} stroke="#faf7ef" strokeWidth="9" fill="none"/>
  <path d={d} stroke={RED} strokeWidth="4" strokeDasharray="8 6" fill="none"/>
  {p>.05&&<path d="M 0 0 L -13 -6 L -13 6 Z" transform={`translate(${tx} ${ty}) rotate(${angle})`} fill={RED}/>} 
 </g>;
};

const Qijiong:React.FC=()=>{
 const frame=useCurrentFrame(), sec=frame/30;
 const beat=data.beats.find(b=>sec>=b.from&&sec<b.to)??data.beats[0];
 const local=frame-beat.from*30;
 const subOp=interpolate(local,[0,8],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
 const jiongOpacity=sec<18?clamp((18-sec)/.5):0;
 const xuOpacity=sec<6?.56*clamp((6-sec)/.8):0;
 const isPalace=sec>=18;
 const pulse=clamp((frame-10*30)/24);
 const fadePulse=sec>=10&&sec<11.2?1-pulse:0;
 const rise=useVerbTiming(frame,30,90),restore=useVerbTiming(frame,19*30,65);
 return <AbsoluteFill style={{background:'#f1ede3',fontFamily:'HistoryMapSerifSC, serif',color:INK}}>
  <style>{`@font-face{font-family:HistoryMapSerifSC;src:url('${staticFile('NotoSerifSC.ttf')}')} *{box-sizing:border-box}`}</style>
  <CameraRig keyframes={data.camera}>
   <Img src={staticFile('core.png')} style={{position:'absolute',inset:0,width:1920,height:1080,filter:'grayscale(.55) saturate(.42) contrast(.7)',opacity:.43}}/>
   <div style={{position:'absolute',inset:0,background:'rgba(240,235,224,.21)'}}/>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0,fontFamily:'HistoryMapSerifSC, serif'}}>
    <Direction frame={frame}/>
    <City record={luo} label="洛阳" detail="汉魏城址附近 · 近似点" active={isPalace}/>
    <City record={yang} label="阳翟" detail="今禹州附近 · 示意点" active={!isPalace} opacity={isPalace?.58*clamp((19-sec)/1):1}/>
    <City record={xu} label="许昌" detail="此前军镇 · 近似参照" opacity={xuOpacity}/>
    <g transform={legacyToCore} opacity={jiongOpacity}>
     <FlagRise at={{lon:yang.coordinates[0],lat:yang.coordinates[1]}} kind="core" timing={rise} color={RED} glyph="冏" label={sec<12?'齐王冏 · 屯兵':undefined}/>
    </g>
    {fadePulse>0&&<circle cx={yx} cy={yy} r={25+pulse*45} fill="none" stroke={RED} strokeWidth="3" opacity={fadePulse}/>} 
    <g transform={legacyToCore}>
     {isPalace&&<FlagRise at={{lon:luo.coordinates[0],lat:luo.coordinates[1]}} kind="core" timing={restore} color="#506f62" glyph="帝" label="惠帝复位"/>}
    </g>
    {sec>=10&&sec<18&&<g transform={`translate(${yx+94} ${yy-14})`} opacity={clamp((sec-10)/.4)}>
     <rect x="-7" y="-26" width="109" height="38" rx="4" fill="#faf6ed" stroke={RED}/>
     <text y="0" fontSize="18" fill={RED}>阳翟战事</text>
    </g>}
   </svg>
  </CameraRig>
  <div style={{position:'absolute',inset:0,pointerEvents:'none',background:'linear-gradient(180deg,rgba(245,240,229,.96),transparent 34%,transparent 83%,rgba(245,240,229,.9))'}}/>
  <header style={{position:'absolute',left:82,top:54,borderLeft:`4px solid ${RED}`,paddingLeft:24}}>
   <div style={{fontSize:18,letterSpacing:5,color:'#847868'}}>八王之乱 · 中原战局</div>
   <div style={{fontSize:52,fontWeight:600,letterSpacing:3,marginTop:6}}>齐王冏起兵讨伦</div>
   <div style={{fontSize:22,marginTop:12,color:'#756a5c'}}>诸王举兵，讨伐司马伦</div>
  </header>
  <div style={{position:'absolute',right:82,top:62,border:`2px solid ${RED}`,padding:'10px 24px',fontSize:34,color:RED}}>公元 301 年</div>
  <div style={{position:'absolute',right:84,top:140,fontSize:17,color:'#756a5c'}}>无声视觉样片 · 西晋</div>
  <div style={{position:'absolute',left:90,top:252,display:'flex',gap:15,alignItems:'center'}}>
   <span style={{width:28,height:2,background:GOLD}}/><span style={{fontSize:26,color:RED}}>{beat.phase}</span>
  </div>
  <div style={{position:'absolute',right:87,top:254,color:'#847868',fontSize:17,textAlign:'center'}}><div style={{fontSize:30}}>↑</div>北</div>
  {sec>=12&&sec<18&&<div style={{position:'absolute',left:90,top:312,fontSize:21,color:'#756a5c'}}>讨伦方向 · 示意</div>}
  {isPalace&&<div style={{position:'absolute',left:90,top:320,width:385,borderTop:`2px solid ${sec>=23?'#506f62':RED}`,paddingTop:18}}>
   <div style={{fontSize:30,color:sec>=23?'#506f62':RED}}>{sec>=23?'司马伦败亡':'王舆等 · 宫廷政变'}</div>
   <div style={{fontSize:20,marginTop:10,color:'#756a5c'}}>{sec>=23?'惠帝恢复帝位':'诛孙秀，逐司马伦'}</div>
  </div>}
  <div style={{position:'absolute',left:120,right:120,bottom:91,background:'rgba(248,245,237,.93)',borderTop:'1px solid #c5b49b',padding:'20px 25px',textAlign:'center',fontSize:34,letterSpacing:2,opacity:subOp}}>{beat.caption}</div>
  <div style={{position:'absolute',left:86,bottom:32,fontSize:15,color:'#807768'}}>现代地形参照 · 城池为近似点 · 不画疆界与精确行军路线</div>
  <div style={{position:'absolute',right:86,bottom:32,fontSize:15,color:'#807768'}}>史据：《晋书》卷四、卷五十九</div>
 </AbsoluteFill>;
};
const Root:React.FC=()=> <Composition id="Qijiong301" component={Qijiong} width={1920} height={1080} fps={30} durationInFrames={780}/>;
registerRoot(Root);
