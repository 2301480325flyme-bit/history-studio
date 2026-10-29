import React from 'react';
import {AbsoluteFill,Audio,Composition,Img,registerRoot,staticFile,useCurrentFrame} from 'remotion';
import scene from './scene.json';

const FPS=30,GOLD='#f7cf70',CYAN='#55dcea',WHITE='#fffdf3';
const clamp=(v:number)=>Math.max(0,Math.min(1,v));
const smooth=(v:number)=>{const p=clamp(v);return p*p*(3-2*p);};
const merc=(lat:number)=>Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
const project=(lon:number,lat:number):[number,number]=>[960+(lon-111.5)*Math.PI/180*12000,540-12000*(merc(lat)-merc(34))];
const place=(id:string)=>scene.places.find(p=>p.id===id)!;
const Y=project(...place('yangzhai_approx').coordinates as [number,number]);
const L=project(...place('luoyang_han_wei').coordinates as [number,number]);
const X=project(...place('xuchang_approx').coordinates as [number,number]);
const seg=scene.segments;
const time=(id:number)=>seg[id].voice_onset;
const strokeText:React.CSSProperties={color:WHITE,WebkitTextStroke:'5px #14171a',paintOrder:'stroke fill',textShadow:'0 3px 5px #0009',fontWeight:700};

function camera(sec:number){
 const ks=scene.camera;const i=ks.findIndex((k,n)=>n<ks.length-1&&sec>=k.t&&sec<=ks[n+1].t);
 const a=ks[Math.max(0,i)],b=ks[Math.min(Math.max(0,i)+1,ks.length-1)];const p=smooth((sec-a.t)/(b.t-a.t));
 return {z:a.z+(b.z-a.z)*p,cx:a.cx+(b.cx-a.cx)*p,cy:a.cy+(b.cy-a.cy)*p};
}
const City:React.FC<{x:number;y:number;name:string;detail:string;active?:boolean;side?:'left'|'right';opacity?:number}>=({x,y,name,detail,active=false,side='right',opacity=1})=>
 <div style={{position:'absolute',left:x,top:y,opacity}}>
  <svg width="52" height="52" style={{position:'absolute',left:-26,top:-26}}><circle cx="26" cy="26" r={active?22:13} fill="#111c27" stroke={active?GOLD:WHITE} strokeWidth="3"/>
   <path d="M18 32V21L26 15L34 21V32Z" fill={active?GOLD:WHITE}/></svg>
  <div style={{position:'absolute',left:side==='left'?-251:32,top:side==='left'?-24:20,width:220,textAlign:side==='left'?'right':'left'}}>
   <div style={{...strokeText,fontSize:34,color:active?GOLD:WHITE}}>{name}</div>
   <div style={{...strokeText,fontSize:18,WebkitTextStroke:'3px #15151b',fontWeight:500,marginTop:1}}>{detail}</div>
  </div>
 </div>;

const Placard:React.FC<{x:number;y:number;name:string;sub:string;portrait?:boolean;green?:boolean;opacity:number}>=({x,y,name,sub,portrait=false,green=false,opacity})=>
 <div style={{position:'absolute',left:x,top:y,width:140,height:226,border:`3px solid ${GOLD}`,borderRadius:3,background:green?'#175a46':'#471c26',boxShadow:'5px 8px 8px #0008',opacity}}>
  <div style={{position:'absolute',left:7,top:7,width:81,height:155,overflow:'hidden',background:'#111a22'}}>
   {portrait?<Img src={staticFile('jiong.png')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 22%'}}/>:
    <svg width="81" height="155"><path d="M13 55Q40 7 67 55L58 59V76Q42 105 25 76V60Z" fill="#d9dfd8"/><path d="M4 147L13 109L28 99L41 119L53 99L70 109L78 147Z" fill="#d9dfd8"/><path d="M11 54H70M41 22V64" stroke="#496c60" strokeWidth="6"/></svg>}
  </div>
  <div style={{position:'absolute',right:5,top:9,writingMode:'vertical-rl',fontFamily:'StorySerif',fontSize:31,fontWeight:600,color:WHITE,letterSpacing:3}}>{name}</div>
  <div style={{position:'absolute',left:6,right:6,top:172,fontSize:21,color:GOLD,textAlign:'center'}}>{sub}</div>
  <div style={{position:'absolute',bottom:5,left:6,right:6,fontSize:13,color:'#e5d7bc',textAlign:'center'}}>{portrait?'AI人物示意像':'军队/宫廷示意牌'}</div>
 </div>;

const Story:React.FC=()=>{
 const frame=useCurrentFrame(),sec=frame/FPS,c=camera(sec);
 const screen=(p:[number,number]):[number,number]=>[960+(p[0]-c.cx)*c.z,540+(p[1]-c.cy)*c.z];
 const [yx,yy]=screen(Y),[lx,ly]=screen(L),[xx,xy]=screen(X);
 const phase=sec<seg[1].file_start?0:sec<seg[2].file_start?1:sec<seg[3].file_start?2:sec<seg[4].file_start?3:sec<seg[5].file_start?4:5;
 const caption=seg.find(s=>frame>=s.caption_from_frame&&frame<s.caption_to_frame);
 const actorIn=smooth((sec-time(1))/.5),actorOut=1-smooth((sec-seg[3].file_end)/.3);
 const direction=clamp((sec-time(2))/Math.max(.1,seg[2].voice_offset-time(2)-.35));
 const arrowVisible=sec>=time(2)&&sec<seg[3].file_start;
 const ex=lx+110,ey=ly+20,cx=(yx+ex)/2+36,cy=(yy+ey)/2-36;
 const ax=(1-direction)**2*yx+2*(1-direction)*direction*cx+direction**2*ex;
 const ay=(1-direction)**2*(yy-12)+2*(1-direction)*direction*cy+direction**2*ey;
 const angle=Math.atan2(2*(1-direction)*(cy-yy+12)+2*direction*(ey-cy),2*(1-direction)*(cx-yx)+2*direction*(ex-cx))*180/Math.PI;
 const battlePulse=clamp((sec-time(3))/.9);
 return <AbsoluteFill style={{background:'#263d4b',fontFamily:'StorySans, sans-serif',overflow:'hidden'}}>
  <style>{`@font-face{font-family:StorySans;src:url('${staticFile('Sans.ttf')}')}@font-face{font-family:StorySerif;src:url('${staticFile('Serif.ttf')}')}*{box-sizing:border-box}`}</style>
  <Audio src={staticFile('mix.wav')}/>
  <svg width="1920" height="1080" style={{position:'absolute',inset:0,overflow:'visible'}}>
   <g transform={`translate(960 540) scale(${c.z}) translate(${-c.cx} ${-c.cy})`}>
    <path d={scene.jin.path} fill="#aa285d" fillRule="evenodd" stroke="#111b25" strokeWidth={12/c.z} strokeLinejoin="round"/>
    <path d={scene.jin.path} fill="none" fillRule="evenodd" stroke={GOLD} strokeWidth={4/c.z} strokeLinejoin="round"/>
    {scene.rivers.map((r,i)=><path key={i} d={r.path} fill="none" stroke={CYAN} strokeWidth={2.6/c.z} strokeOpacity=".9" strokeLinecap="round" strokeLinejoin="round"/>)}
   </g>
  </svg>
  <div style={{...strokeText,position:'absolute',left:640-550*smooth((c.z-.3)/.5),top:617,fontFamily:'StorySerif',fontSize:114,letterSpacing:13,opacity:.8}}>西晋</div>
  <div style={{position:'absolute',inset:0,pointerEvents:'none',background:'linear-gradient(180deg,#08111b9c,transparent 19%,transparent 73%,#080b13b5)'}}/>
  <header style={{position:'absolute',left:48,top:27,color:WHITE}}>
   <div style={{fontSize:20,letterSpacing:3,color:GOLD}}>八王之乱 · 中原战局</div>
   <div style={{...strokeText,fontSize:40,marginTop:5}}>齐王冏起兵讨伦</div>
  </header>
  <div style={{position:'absolute',right:45,top:24,color:GOLD,fontSize:42,fontWeight:700}}>公元301年</div>
  <div style={{position:'absolute',right:47,top:83,fontSize:21,color:WHITE,background:'#101824cc',padding:'8px 13px',borderLeft:`4px solid ${GOLD}`}}>晋域：300年低精度快照 · 非301年精确疆界</div>
  <div style={{position:'absolute',left:51,top:143,color:GOLD,fontSize:27,fontWeight:600}}>{['正月 · 司马伦篡位','三月 · 阳翟起兵','诸王响应 · 讨伦方向','四月 · 阳翟战事','四月 · 洛阳宫变','惠帝复位 · 伦败亡'][phase]}</div>
  <City x={lx} y={ly} name="洛阳" detail="汉魏城址附近·近似点" active={phase===0||phase>=4} side="left"/>
  {(phase>=1&&phase<=3||phase===5)&&<City x={yx} y={yy} name="阳翟" detail="今禹州附近·示意点" active={phase<=3}/>}
  {phase===1&&<div style={{...strokeText,position:'absolute',left:52,top:192,fontSize:23,color:'#ddd5d2'}}>此前军镇：许昌（近似参照）</div>}
  {sec>=time(1)&&sec<seg[4].file_start&&<svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d={`M${yx} ${yy-23}L${yx+88} ${yy-19}`} stroke={GOLD} strokeWidth="2" fill="none" opacity={actorIn*actorOut}/></svg>}
  {sec>=time(1)&&sec<seg[4].file_start&&<Placard x={yx+88} y={yy-245} name="齐王冏" sub="阳翟屯兵" portrait opacity={actorIn*actorOut}/>}
  {arrowVisible&&<>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d={`M${yx} ${yy-12} Q${cx} ${cy} ${ax} ${ay}`} fill="none" stroke="#16151b" strokeWidth="14"/><path d={`M${yx} ${yy-12} Q${cx} ${cy} ${ax} ${ay}`} fill="none" stroke={GOLD} strokeWidth="7" strokeDasharray="16 9"/>{direction>.08&&<path d="M0 0L-22 -10L-22 10Z" fill={GOLD} stroke="#16151b" strokeWidth="2" transform={`translate(${ax} ${ay}) rotate(${angle})`}/>}</svg>
   <div style={{...strokeText,position:'absolute',left:52,top:192,fontSize:25,color:GOLD}}>讨伦方向 · 示意</div>
  </>}
  {phase===3&&<>
   <svg width="1920" height="1080" style={{position:'absolute',inset:0}}>{battlePulse<1&&<circle cx={yx} cy={yy} r={30+battlePulse*55} fill="none" stroke={GOLD} strokeWidth="5" opacity={1-battlePulse}/>}</svg>
   <div style={{position:'absolute',left:yx-245,top:yy-137,width:168,padding:'13px 7px',color:WHITE,background:'#193249',border:`3px solid ${CYAN}`,boxShadow:'4px 6px 6px #0007',textAlign:'center'}}><div style={{fontSize:29}}>张泓军</div><div style={{fontSize:26,color:GOLD,marginTop:8}}>阳翟败退</div></div>
  </>}
  {phase>=4&&<svg width="1920" height="1080" style={{position:'absolute',inset:0}}><path d={`M${lx} ${ly-23}L${lx+92} ${ly-19}`} stroke={GOLD} strokeWidth="2" fill="none" opacity={smooth((sec-time(phase))/.4)}/></svg>}
  {phase===4&&<Placard x={lx+92} y={ly-245} name="王舆等" sub="宫廷政变" green opacity={smooth((sec-time(4))/.4)}/>}
  {phase===5&&<Placard x={lx+92} y={ly-245} name="惠帝" sub="恢复帝位" green opacity={smooth((sec-time(5))/.4)}/>}
  <div style={{position:'absolute',left:50,right:50,bottom:39,fontSize:20,color:'#e1eff3',display:'flex',justifyContent:'space-between'}}><span>城池近似/示意 · 河流为现代参照 · 不复原古河道</span><span>{phase<3?'史据：《晋书》卷四/五十九':'史据：《晋书》卷四 · 永宁元年'}</span></div>
  <div style={{position:'absolute',right:49,bottom:89,color:CYAN,fontSize:18}}><span style={{display:'inline-block',width:40,height:3,background:CYAN,verticalAlign:'middle',marginRight:10}}/>河流 · 现代地理参照</div>
  {caption&&<div style={{...strokeText,position:'absolute',left:50,right:50,bottom:125,fontSize:48,textAlign:'center',letterSpacing:1,lineHeight:1.25}}>{caption.caption}</div>}
 </AbsoluteFill>;
};
const Root:React.FC=()=> <Composition id="QijiongWhitehong301" component={Story} width={1920} height={1080} fps={FPS} durationInFrames={780}/>;
registerRoot(Root);
