import React from 'react';
import {AbsoluteFill,Audio,Composition,Img,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import scene from './scene.json';
const FPS=30,RED='#c8241b',BLUE='#2878ac',INK='#392c23',GOLD='#dec083';
const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const smooth=(v:number)=>{const p=clamp(v);return p*p*(3-2*p);};
const merc=(lat:number)=>Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
const project=(lon:number,lat:number):[number,number]=>[960+(lon-111.5)*Math.PI/180*12000,540-12000*(merc(lat)-merc(34))];
const place=(id:string)=>scene.places.find(p=>p.id===id)!;
const Y=project(...place('yangzhai_approx').coordinates as [number,number]),L=project(...place('luoyang_han_wei').coordinates as [number,number]),X=project(...place('xuchang_approx').coordinates as [number,number]);
const seg=scene.segments;
function camera(sec:number){
 const ks=scene.camera;const i=ks.findIndex((k,n)=>n<ks.length-1&&sec>=k.t&&sec<=ks[n+1].t);
 const a=ks[Math.max(0,i)],b=ks[Math.min(Math.max(0,i)+1,ks.length-1)],p=smooth((sec-a.t)/(b.t-a.t));
 return {z:a.z+(b.z-a.z)*p,cx:a.cx+(b.cx-a.cx)*p,cy:a.cy+(b.cy-a.cy)*p};
}
const Label:React.FC<{x:number;y:number;name:string;detail:string;dx:number;dy:number;active?:boolean}>=({x,y,name,detail,dx,dy,active=false})=>
 <div style={{position:'absolute',left:x,top:y,color:INK}}>
  <svg width="26" height="26" style={{position:'absolute',left:-13,top:-13}}><circle cx="13" cy="13" r={active?10:7} fill={active?RED:'#463526'} stroke="#fff0d0" strokeWidth="2"/></svg>
  {y+dy+72<880&&y+dy>140&&<div style={{position:'absolute',left:dx,top:dy,width:270,textShadow:'1px 1px 2px #fff5dc',fontSize:active?35:27,fontWeight:700}}>{name}<div style={{fontSize:16,fontWeight:500,marginTop:3}}>{detail}</div></div>}
 </div>;
const Flag:React.FC<{x:number;y:number;name:string;sub:string;blue?:boolean;opacity:number}>=({x,y,name,sub,blue=false,opacity})=>
 <div style={{position:'absolute',left:x,top:y,width:108,height:220,opacity,color:'#fbe5b6'}}>
  <svg width="108" height="220"><path d="M6 210V8M0 12H105" stroke="#7e582b" strokeWidth="5"/><path d="M14 18H98V149L56 139L14 149Z" fill={blue?'#27587e':'#8a281c'} stroke={GOLD} strokeWidth="4"/><path d="M8 7L16 0L24 7" fill={GOLD}/></svg>
  <div style={{position:'absolute',left:38,top:28,writingMode:'vertical-rl',fontFamily:'StorySerif',fontSize:32,letterSpacing:4,fontWeight:700}}>{name}</div>
  <div style={{position:'absolute',left:-3,top:164,background:'#493b2ddb',padding:'6px 8px',whiteSpace:'nowrap',fontSize:20}}>{sub}</div>
  <div style={{position:'absolute',left:14,top:205,fontSize:13,whiteSpace:'nowrap',color:'#224c70',background:'#efe0c9e8',padding:'2px 5px'}}>地点关联 · 示意</div>
 </div>;
const Story:React.FC=()=>{
 const f=useCurrentFrame(),sec=f/FPS,c=camera(sec);
 const screen=(p:[number,number]):[number,number]=>[960+(p[0]-c.cx)*c.z,540+(p[1]-c.cy)*c.z];
 const [yx,yy]=screen(Y),[lx,ly]=screen(L),[xx,xy]=screen(X);
 const phase=sec<seg[1].file_start?0:sec<seg[2].file_start?1:sec<seg[3].file_start?2:sec<seg[4].file_start?3:sec<seg[5].file_start?4:5;
 const cap=seg.find(s=>f>=s.caption_from_frame&&f<s.caption_to_frame);
 const portrait=smooth((sec-seg[1].voice_onset)/.35)*(1-smooth((sec-7.2)/.45));
 const actor=smooth((sec-seg[1].voice_onset)/.5)*(1-smooth((sec-seg[3].file_end)/.3));
 const progress=clamp((sec-seg[2].voice_onset)/(seg[2].voice_offset-seg[2].voice_onset-.35));
 const arrow=sec>=seg[2].voice_onset&&sec<seg[3].file_start;
 // Stop short of the Luo marker: this is a narrative direction, not a march into its palace.
 const ex=lx+128,ey=ly+90,cx=(yx+ex)/2-65,cy=(yy+ey)/2+15;
 const ax=(1-progress)**2*yx+2*(1-progress)*progress*cx+progress**2*ex;
 const ay=(1-progress)**2*(yy-15)+2*(1-progress)*progress*cy+progress**2*ey;
 const angle=Math.atan2(2*(1-progress)*(cy-yy+15)+2*progress*(ey-cy),2*(1-progress)*(cx-yx)+2*progress*(ex-cx))*180/Math.PI;
 const pulse=clamp((sec-seg[3].voice_onset)/.9);
 const relation=smooth((sec-seg[1].voice_onset)/1);
 const courtFlagY=Math.max(165,ly-265);
 return <AbsoluteFill style={{background:'#d6c4a9',fontFamily:'StorySans',overflow:'hidden'}}>
  <style>{`@font-face{font-family:StorySans;src:url('${staticFile('Sans.ttf')}')}@font-face{font-family:StorySerif;src:url('${staticFile('Serif.ttf')}')}*{box-sizing:border-box}`}</style>
  <Audio src={staticFile('mix.wav')}/>
  <div style={{position:'absolute',left:0,top:0,width:1920,height:1080,transformOrigin:'0 0',transform:`translate(960px,540px) scale(${c.z}) translate(${-c.cx}px,${-c.cy}px)`}}>
   <Img src={staticFile('relief.png')} style={{position:'absolute',left:scene.raster.x,top:scene.raster.y,width:scene.raster.width,height:scene.raster.height}}/>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0,overflow:'visible'}}>{scene.rivers.map((r,i)=><path key={i} d={r.path} fill="none" stroke={BLUE} strokeWidth={2.8/c.z} strokeOpacity=".9" strokeLinecap="round"/>)}</svg>
  </div>
  <div style={{position:'absolute',inset:0,background:'linear-gradient(180deg,#1b180c21,transparent 18%,transparent 72%,#24190f18)'}}/>
  <div style={{position:'absolute',left:50,top:27,color:INK,fontSize:19,letterSpacing:3}}>西晋 · 中原 / 八王之乱</div>
  <div style={{position:'absolute',left:50,top:61,fontFamily:'StorySerif',fontSize:36,color:INK,fontWeight:700}}>齐王冏起兵讨伦</div>
  <div style={{position:'absolute',right:44,top:32,color:'#fff4d6',background:'#594431e8',padding:'10px 23px',border:'1px solid #c7a86d',fontSize:29}}>{['正月 · 篡位','三月 · 阳翟起兵','诸王响应','四月 · 阳翟战事','四月 · 洛阳宫变','惠帝复位'][phase]}</div>
  <div style={{position:'absolute',left:30,top:300,fontFamily:'StorySerif',fontSize:65,color:'#765b3870',writingMode:'vertical-rl',letterSpacing:8}}>西晋</div>
  <Label x={lx} y={ly} name="洛阳" detail="汉魏城址附近·近似点" dx={-225} dy={-15} active={phase===0||phase>=4}/>
  <Label x={yx} y={yy} name="阳翟" detail="今禹州附近·示意点" dx={-120} dy={31} active={phase>=1&&phase<=3}/>
  <Label x={xx} y={xy} name="许昌" detail="此前军镇·近似参照" dx={42} dy={24}/>
  {phase>=1&&phase<=3&&<>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d={`M${yx} ${yy}L${yx+130*relation} ${yy-60*relation}`} strokeDasharray="8 7" fill="none" stroke={BLUE} strokeWidth="2"/><circle cx={yx} cy={yy} r="18" fill="none" stroke={BLUE} strokeWidth="2"/></svg>
   <Flag x={yx+127} y={yy-265} name="齐王冏" sub="阳翟屯兵" opacity={actor}/>
  </>}
  {arrow&&<>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0}}><defs><filter id="glow"><feGaussianBlur stdDeviation="5"/></filter></defs><path d={`M${yx} ${yy-15}Q${cx} ${cy} ${ax} ${ay}`} fill="none" stroke="#e93716" strokeWidth="19" opacity=".45" filter="url(#glow)"/><path d={`M${yx} ${yy-15}Q${cx} ${cy} ${ax} ${ay}`} fill="none" stroke={RED} strokeWidth="7"/>{progress>.05&&<path d="M1 0L-28 -13L-22 0L-28 13Z" fill={RED} transform={`translate(${ax} ${ay}) rotate(${angle})`}/>}</svg>
   <div style={{position:'absolute',left:58,top:155,fontSize:24,color:RED,background:'#f1dfbcdd',padding:'9px 15px',borderLeft:`4px solid ${RED}`}}>讨伦方向 · 示意</div>
  </>}
  {phase===3&&<><svg width="1920" height="1080" style={{position:'absolute',inset:0}}>{pulse<1&&<circle cx={yx} cy={yy} r={24+pulse*60} stroke={RED} strokeWidth="5" fill="none" opacity={1-pulse}/>}</svg><div style={{position:'absolute',left:yx-310,top:yy-135,width:232,padding:'12px 16px',color:'#fff3d8',background:'#653622eb',fontSize:27,border:'2px solid #be8758'}}>冏将击张泓<br/><b style={{fontSize:33,whiteSpace:'nowrap'}}>阳翟大破之</b></div></>}
  {phase>=4&&<><svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d={`M${lx} ${ly}L${lx+130*smooth((sec-seg[phase].voice_onset)/.65)} ${ly+(courtFlagY+209-ly)*smooth((sec-seg[phase].voice_onset)/.65)}`} fill="none" stroke={BLUE} strokeWidth="2" strokeDasharray="8 7"/></svg><Flag x={lx+128} y={courtFlagY} name={phase===4?'王舆等':'惠帝'} sub={phase===4?'诛秀逐伦':'恢复帝位'} blue opacity={smooth((sec-seg[phase].voice_onset)/.4)}/></>}
  {portrait>0&&<><div style={{position:'absolute',inset:0,background:'#111318',opacity:portrait*.55}}/><div style={{position:'absolute',left:80,top:200,width:270,height:470,opacity:portrait,boxShadow:'0 12px 38px #0008',border:'2px solid #d8bc80',background:'#252225'}}><div style={{height:365,overflow:'hidden'}}><Img src={staticFile('jiong.png')} style={{width:'100%',height:405,objectFit:'cover',objectPosition:'50% 20%'}}/></div><div style={{color:'#f2deaa',fontFamily:'StorySerif',fontSize:39,textAlign:'center',marginTop:10}}>齐王 · 司马冏</div><div style={{color:'#dfd2be',fontSize:16,textAlign:'center',marginTop:3}}>AI人物示意像</div></div></>}
  <div style={{position:'absolute',left:26,bottom:106,width:166,padding:'10px 10px',background:'#38555dde',color:'#fff2d1',border:'1px solid #d3b989',borderRadius:5,textAlign:'center',fontSize:32,fontWeight:700}}>301年</div>
  <div style={{position:'absolute',left:207,right:25,bottom:105,minHeight:89,background:'#1e1e1bd9',borderTop:'1px solid #b2a184',padding:'14px 23px',fontSize:44,color:'#fffaf0',textAlign:'center',lineHeight:1.3}}>{cap?.caption||' '}</div>
  <div style={{position:'absolute',left:28,bottom:66,color:'#274f6b',fontSize:17,background:'#e8dcc4d9',padding:'3px 7px'}}>蓝实线：现代河流　蓝虚线：地点—旗牌示意关联</div>
  <footer style={{position:'absolute',left:27,right:27,bottom:22,color:'#443c30',fontSize:17,display:'flex',justifyContent:'space-between'}}><span>城池近似 / 示意点 · 现代地形水系参照，非古河道复原</span><span>史据：《晋书》卷四 / 五十九　底图：Esri, USGS, NOAA · 河网：Natural Earth</span></footer>
 </AbsoluteFill>;
};
const Root:React.FC=()=> <Composition id="QijiongZhitanxia301" component={Story} width={1920} height={1080} fps={FPS} durationInFrames={780}/>;
registerRoot(Root);
