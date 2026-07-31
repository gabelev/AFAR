// AFAR pixel engine — tile-grid world, sprites, era palette remaps
export const PAL = {
  void:'#0e1013', rain:'#1b2027',
  wallCap:'#1e2126', wallFace:'#4b4f57',
  conc:'#383b40', concD:'#33363b',
  floor:'#463d31', floorD:'#3c342a',
  rug:'#544130', rugD:'#463628',
  wood:'#5c4b37', woodD:'#443726',
  ink:'#16140f', paper:'#d6cfbc', paperD:'#a9a290',
  lamp:'#e0b25a', metal:'#6a6f78', metalD:'#43474e',
  glass:'#31404c', skin:'#c39a7d', hair:'#292319',
  staff:'#8b8577', staffD:'#5e5a4f',
  evers:'#a34c2e', eversD:'#6e3220',
  roan:'#71917d', roanD:'#4b6355',
  delta:'#bd9040', deltaD:'#7c5e2a',
  asph:'#2b2e34', asphD:'#262a2f',
  pave:'#4a463d', paveD:'#403c34', curb:'#5a5449',
  guest:'#8a6f9e', guestD:'#5e4a6c'
};
// Era B = same world through a LUT: 8 entries remapped, everything else untouched
export function eraPal(era){
  if(era!=='B') return PAL;
  return Object.assign({}, PAL, {
    void:'#13100b', rain:'#13100b', glass:'#4d4026',
    floor:'#4b4033', floorD:'#403629', conc:'#3d3a33', concD:'#37342d',
    wallFace:'#55503f', lamp:'#d8a248',
    asph:'#302d27', asphD:'#2a2722',
    pave:'#4d4536', paveD:'#423b2e', curb:'#5c5240'
  });
}
export const SWATCHES=[
  ['void / night','void'],['rain streak','rain'],['wall cap','wallCap'],['wall face','wallFace'],
  ['concrete (studios)','conc'],['floorboard','floor'],['archive rug','rug'],['furniture wood','wood'],
  ['ink / outline','ink'],['paper','paper'],['lamp','lamp'],['metal','metal'],['glass','glass'],
  ['Evers Lane — oxide','evers'],['Roan Patina — verdigris','roan'],['Delta Marlowe — ochre','delta']
];
const T=16,W=33,H=34;
function P(c,x,y,w,h,col){c.fillStyle=col;c.fillRect(x,y,w,h);}
function box(c,x,y,w,h,fill,edge){P(c,x,y,w,h,edge);P(c,x+1,y+1,w-2,h-2,fill);}
function disc(c,cx,cy,r,col){for(let dy=-r;dy<=r;dy++){const w=Math.floor(Math.sqrt(r*r-dy*dy));P(c,cx-w,cy+dy,2*w+1,1,col);}}
function ring(c,cx,cy,r,col,step){for(let a=0;a<360;a+=step){const x=Math.round(cx+r*Math.cos(a*Math.PI/180)),y=Math.round(cy+r*Math.sin(a*Math.PI/180));P(c,x,y,1,1,col);}}

// ---- sprites: 16x16 maps. . none / o ink / c coat / d coat-dark / s skin / h hair / p paper / m metal
const S={
evers:{down:[
"................","......oooo......",".....odddddo....","...ooddddddoo...",
"....osssssso....","....osossoso....",".....osssso.....","....occccco.....",
"...occccccco....","...occcpccco....","...occcoccco....","...odccoccdo....",
"...odccoccdo....","...odcccccdo....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....odddddo....","...ooddddddoo...",
"....osssso......","....ososso......",".....ossso......","....occcco......",
"....occccco.....","....ocdccco.....","....ocdccco.....","....ocdccco.....",
"....occccco.....","....odcccdo.....",".....oo.oo......","................"],
up:["................","......oooo......",".....odddddo....","...ooddddddoo...",
"....odddddo.....","....odddddo.....",".....odddo......","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"]},
roan:{down:[
"................","................","......ooo.......",".....occco......",
".....ocsso......",".....ososo......","......oss.......",".....occc.o.....",
".....occcco.....","......occo......",".....occ.co.....","......occo......",
"......oc.o......","......o..o......","......o..o......","................"],
side:[
"................","................","......ooo.......",".....occco......",
".....oscco......",".....oosco......","......oso.......",".....occ.o......",
".....occco......","......occo......",".....oc.co......","......occo......",
"......o.co......","......o..o......","......oo........","................"],
up:["................","................","......ooo.......",".....occco......",
".....occco......",".....occco......","......occ.......",".....occc.o.....",
".....occcco.....","......occo......",".....occ.co.....","......occo......",
"......oc.o......","......o..o......","......o..o......","................"]},
delta:{down:[
"................","................",".....ohhho......",".....ohhho......",
".....osssso.....",".....ososso.....","...oodddddoo....","..occcccccco....",
"..occdccdcco....","..occcccccco....","..odccccccdo....","..occcccccco....",
"..odccccccdo....","...occ..cco.....","...oo....oo.....","................"],
side:[
"................","................",".....ohhho......",".....ohhho......",
".....ossso......",".....oosso......","....occccoo.....","...occccccco....",
"...ocdccdcco....","...occccccco....","...odcccccdo....","...occccccco....",
"...odccccdo.....","....occ.cco.....","....oo...oo.....","................"],
up:["................","................",".....ohhho......",".....ohhho......",
".....ohhhho.....",".....ohhhho.....","...oocccccoo....","..occcccccco....",
"..occdccdcco....","..occcccccco....","..odccccccdo....","..occcccccco....",
"..odccccccdo....","...occ..cco.....","...oo....oo.....","................"]},
producer:{down:[
"................","......oooo......",".....ommmmo.....","....omhhhhmo....",
"....omssssmo....","....omsossmo....",".....osssso.....","....occccco.....",
"...occccccco....","...occcmccco....","...occccccco....","...odcccccdo....",
"....occccco.....","....occccco.....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....ommmmo.....","....omhhhho.....",
"....omsssso.....","....omsosso.....",".....ossso......","....occcco......",
"....occccco.....","....ocmccco.....","....occccco.....","....odcccdo.....",
"....occcco......","....occcco......",".....oo.oo......","................"],
up:[
"................","......oooo......",".....ommmmo.....","....omhhhhmo....",
"....omhhhhmo....","....omhhhhmo....",".....ohhhho.....","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"....occccco.....","....occccco.....","....oo...oo.....","................"]},
critic:{down:[
"................","................","......ohho......",".....ohhhho.....",
".....ommmmo.....","......osso......",".....occcco.....",".....occcco.....",
"...ppocccco.....","...ppocccco.....",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....oo..oo.....","................"],
side:[
"................","................","......ohho......",".....ohhho......",
".....ommo.......",".....osso.......",".....occco......",".....occco......",
"...ppoccco......","...ppoccco......",".....occco......",".....occco......",
".....occco......",".....occco......",".....oo.oo......","................"],
up:[
"................","................","......ohho......",".....ohhhho.....",
".....ohhhho.....","......ohho......",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....occcco.....",".....occcco.....",
".....occcco.....",".....occcco.....",".....oo..oo.....","................"]},
listener:{down:[
"................","................","......ohho......",".....ossso......",
".....ososo......","....occccco.....","...occccccco....","...occccccco....",
"...occccccco....","...occccccco....","...occccccco....","....occccco.....",
"....occccco.....","....occccco.....","....oo...oo.....","................"],
side:[
"................","................","......ohho......",".....ossso......",
".....oosso......","....occcco......","...occcccco.....","...occcccco.....",
"...occcccco.....","...occcccco.....","...occcccco.....","....occcco......",
"....occcco......","....occcco......","....oo..oo......","................"],
up:[
"................","................","......ohho......",".....ohhho......",
".....ohhho......","....occccco.....","...occccccco....","...occccccco....",
"...occccccco....","...occccccco....","...occccccco....","....occccco.....",
"....occccco.....","....occccco.....","....oo...oo.....","................"]},
muse:{down:[
"................",".....ohhho......","....ohhhhho.....","....ohsssho.....",
"....ohsosho.....","....ohsssho.....","....ohpppho.....","....ohpppho.....",
"....ohpppho.....",".....opppo......",".....opppo......",".....opppo......",
".....opppo......",".....opppo......",".....oo.oo......","................"],
side:[
"................",".....ohhho......","....ohhhho......","....ohssso......",
"....ohsoso......","....ohssso......","....ohpppo......","....ohpppo......",
"....ohpppo......",".....oppo.......",".....oppo.......",".....oppo.......",
".....oppo.......",".....oppo.......",".....oo.oo......","................"],
up:[
"................",".....ohhho......","....ohhhhho.....","....ohhhhho.....",
"....ohhhhho.....","....ohhhhho.....","....ohpppho.....","....ohpppho.....",
"....ohpppho.....",".....opppo......",".....opppo......",".....ohhho......",
".....opppo......",".....opppo......",".....oo.oo......","................"]},
vess:{down:[
"................","......oooo......",".....oddddo.....","....oddddddo....",
"....osssssso....","....osossoso....",".....osssso.....","....occccco.....",
"...occccccco....","...ocpcccpco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"],
side:[
"................","......oooo......",".....oddddo.....","....odddddo.....",
"....osssso......","....ososso......",".....ossso......","....occcco......",
"....occccco.....","....ocpccco.....","....occccco.....","....odcccdo.....",
"....occccco.....","....odcccdo.....",".....oo.oo......","................"],
up:[
"................","......oooo......",".....oddddo.....","....oddddddo....",
"....oddddddo....","....oddddddo....",".....odddo......","....occccco.....",
"...occccccco....","...occccccco....","...occccccco....","...odcccccdo....",
"...odcccccdo....","...odcccccdo....","....oo...oo.....","................"]}
};
function dict(p,who){
  const acc={evers:[p.evers,p.eversD],roan:[p.roan,p.roanD],delta:[p.delta,p.deltaD],vess:[p.guest,p.guestD]}[who]||[p.staff,p.staffD];
  return {o:p.ink,c:acc[0],d:acc[1],s:p.skin,h:p.hair,p:p.paper,m:p.metal};
}
function drawMap(c,map,px,py,dk,flip){
  for(let y=0;y<16;y++){const row=map[y]||'';
    for(let x=0;x<16;x++){const ch=row[flip?15-x:x];const col=dk[ch];if(col)P(c,px+x,py+y,1,1,col);}}
}
function frames(map){
  const A=map;
  const B=map.map((r,y)=>y===14?r.slice(0,8)+'........':r);
  const C=map.map((r,y)=>y===14?'........'+r.slice(8):r);
  return [A,B,C];
}
function sprite(c,who,tx,ty,dir,p){
  const s=S[who];const flip=dir==='right';
  const map=s[dir==='right'?'side':(dir||'down')]||s.down;
  drawMap(c,map,Math.round(tx*T),Math.round(ty*T)-6,dict(p,who),flip);
}

// ---- props
function desk(c,tx,ty,w,p){box(c,tx*T,ty*T,w*T,22,p.wood,p.ink);P(c,tx*T+2,ty*T+2,w*T-4,4,p.woodD);}
function consoleDesk(c,tx,ty,w,p,acc){desk(c,tx,ty,w,p);
  for(let i=0;i<w*4-2;i++)P(c,tx*T+4+i*4,ty*T+10,2,2,i%5===2?acc:p.metal);
  P(c,tx*T+4,ty*T+16,w*T-8,2,p.metalD);}
function reels(c,tx,ty,p){box(c,tx*T,ty*T,30,14,p.metalD,p.ink);disc(c,tx*T+8,ty*T+7,4,p.metal);disc(c,tx*T+21,ty*T+7,4,p.metal);P(c,tx*T+7,ty*T+6,2,2,p.ink);P(c,tx*T+20,ty*T+6,2,2,p.ink);}
function shelf(c,tx,ty,w,p){box(c,tx*T,ty*T,w*T,15,p.woodD,p.ink);
  const cols=[p.paperD,p.eversD,p.roanD,p.deltaD,p.metalD,p.paper];
  for(let i=0;i<Math.floor((w*T-6)/3);i++)P(c,tx*T+3+i*3,ty*T+3,2,10,cols[(i*7+tx+ty)%6]);}
function turntable(c,tx,ty,p,playing){box(c,tx*T,ty*T,32,30,p.wood,p.ink);
  disc(c,tx*T+15,ty*T+14,11,p.metalD);disc(c,tx*T+15,ty*T+14,9,p.ink);
  disc(c,tx*T+15,ty*T+14,3,playing?p.lamp:p.paperD);P(c,tx*T+15,ty*T+14,1,1,p.ink);
  P(c,tx*T+26,ty*T+4,2,12,p.metal);P(c,tx*T+22,ty*T+14,5,2,p.metal);}
function chair(c,tx,ty,p){box(c,tx*T+3,ty*T+3,10,10,p.wood,p.ink);P(c,tx*T+4,ty*T+4,8,2,p.woodD);}
function armchair(c,tx,ty,p){box(c,tx*T+1,ty*T+1,22,20,p.staffD,p.ink);P(c,tx*T+4,ty*T+5,16,12,p.staff);P(c,tx*T+2,ty*T+2,20,3,p.staffD);}
function lampPool(c,tx,ty,p){c.globalAlpha=0.14;disc(c,tx*T+8,ty*T+8,22,p.lamp);c.globalAlpha=0.3;disc(c,tx*T+8,ty*T+8,12,p.lamp);c.globalAlpha=1;
  disc(c,tx*T+8,ty*T+8,4,p.lamp);ring(c,tx*T+8,ty*T+8,5,p.ink,45);}
function crate(c,tx,ty,p){box(c,tx*T+2,ty*T+3,12,11,p.wood,p.ink);P(c,tx*T+3,ty*T+8,10,1,p.woodD);P(c,tx*T+7,ty*T+4,1,9,p.woodD);}
function ghost(c,tx,ty,w,h,p){c.globalAlpha=0.35;
  for(let x=0;x<w*T;x+=4){P(c,tx*T+x,ty*T,2,1,p.paperD);P(c,tx*T+x,ty*T+h*T-1,2,1,p.paperD);}
  for(let y=0;y<h*T;y+=4){P(c,tx*T,ty*T+y,1,2,p.paperD);P(c,tx*T+w*T-1,ty*T+y,1,2,p.paperD);}
  c.globalAlpha=1;}
function puddle(c,tx,ty,p){disc(c,tx*T+7,ty*T+9,4,p.glass);disc(c,tx*T+11,ty*T+7,2,p.glass);P(c,tx*T+5,ty*T+7,3,1,p.paperD);}
function papers(c,tx,ty,p){P(c,tx*T+2,ty*T+4,7,5,p.paperD);P(c,tx*T+5,ty*T+2,7,5,p.paper);P(c,tx*T+6,ty*T+3,5,1,p.paperD);}
function windowV(c,tx,ty,p){P(c,tx*T+10,ty*T+1,5,14,p.ink);P(c,tx*T+11,ty*T+2,3,12,p.glass);P(c,tx*T+11,ty*T+8,3,1,p.ink);}
function cable(c,pts,p){for(let i=0;i<pts.length-1;i++){const[a,b]=[pts[i],pts[i+1]];
  const n=Math.max(Math.abs(b[0]-a[0]),Math.abs(b[1]-a[1]));
  for(let k=0;k<=n;k++)P(c,Math.round(a[0]+(b[0]-a[0])*k/n),Math.round(a[1]+(b[1]-a[1])*k/n),1,1,p.ink);}}

// ---- world
function grid(){
  const g=Array.from({length:H},()=>Array(W).fill('V'));
  const fill=(x1,y1,x2,y2,t)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)g[y][x]=t;};
  fill(1,2,31,32,'W');
  fill(2,3,10,10,'S');fill(12,3,20,10,'S');fill(22,3,30,10,'S');
  fill(2,12,30,14,'C');fill(2,16,13,31,'O');fill(15,16,30,31,'A');
  fill(19,21,26,27,'R');
  g[11][6]='C';g[11][16]='C';g[11][26]='C';g[15][7]='O';g[15][22]='A';
  return g;
}
function paint(c,p,scene,era){
  const g=grid();
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const t=g[y][x],px=x*T,py=y*T;
    if(t==='V'){P(c,px,py,T,T,p.void);
      if(era!=='B'&&(x*13+y*29)%31<2){P(c,px+3,py+2,1,4,p.rain);P(c,px+9,py+9,1,4,p.rain);}
    }else if(t==='W'){P(c,px,py,T,T,p.wallCap);
      const below=g[y+1]&&g[y+1][x];
      if(below&&below!=='W'&&below!=='V'){P(c,px,py+6,T,10,p.wallFace);P(c,px,py+15,T,1,p.ink);P(c,px,py+5,T,1,p.ink);}
    }else if(t==='S'){P(c,px,py,T,T,p.conc);if(y%2===0)P(c,px,py,T,1,p.concD);if((x*5+y*11)%13===0)P(c,px+3,py+8,5,1,p.concD);
    }else if(t==='R'){P(c,px,py,T,T,p.rug);if((x+y)%2)P(c,px+4,py+4,2,2,p.rugD);
      if(g[y][x-1]!=='R')P(c,px,py,1,T,p.rugD);if(g[y][x+1]!=='R')P(c,px+15,py,1,T,p.rugD);
      if(g[y-1][x]!=='R')P(c,px,py,T,1,p.rugD);if(g[y+1][x]!=='R')P(c,px,py+15,T,1,p.rugD);
    }else{P(c,px,py,T,T,p.floor);P(c,px,py+(y%2?7:15),T,1,p.floorD);P(c,px+((x*7+y*3)%3)*5+2,py,1,7,p.floorD);}
  }
  // door thresholds
  [[6,11],[16,11],[26,11],[7,15],[22,15]].forEach(([x,y])=>{P(c,x*T,y*T+1,T,2,p.woodD);P(c,x*T,y*T+13,T,2,p.woodD);});
  // Studio A — Evers Lane: everything aligned
  shelf(c,3,3,3,p);reels(c,7,3,p);consoleDesk(c,3,5,4,p,p.evers);chair(c,7,6,p);crate(c,9,8,p);crate(c,9,9,p);papers(c,4,8,p);
  // Studio B — Roan Patina: sparse, dust ghosts where gear was removed
  desk(c,15,5,2,p);ghost(c,13,8,1,1,p);ghost(c,17,8,2,1,p);papers(c,15,9,p);
  if(era==='B')ghost(c,18,4,1,1,p);else crate(c,18,4,p);
  // Studio C — Delta Marlowe: crowded, stacked
  consoleDesk(c,23,4,3,p,p.delta);desk(c,27,6,2,p);crate(c,23,8,p);crate(c,24,8,p);crate(c,23,9,p);crate(c,29,3,p);crate(c,29,4,p);papers(c,27,9,p);papers(c,26,3,p);
  cable(c,[[23*T+8,6*T],[24*T,8*T-2],[27*T+4,7*T+6]],p);
  // Office
  shelf(c,8,16,4,p);desk(c,4,20,3,p);papers(c,5,20,p);reels(c,5,20.4,p);
  desk(c,9,17,2,p);papers(c,9,17,p);
  armchair(c,4,26,p);lampPool(c,3,25,p);windowV(c,1,23,p);windowV(c,1,24,p);
  // Archive / listening room
  shelf(c,16,16,5,p);shelf(c,24,16,6,p);
  turntable(c,21,22,p,scene==='listening');lampPool(c,19,22,p);
  armchair(c,25,25,p);crate(c,16,29,p);crate(c,17,29,p);
  if(era==='B'){crate(c,18,29,p);crate(c,16,28,p);}
  else{puddle(c,10,13,p);puddle(c,24,13,p);}
  // people
  sprite(c,'producer',5,22,'up',p);sprite(c,'critic',10.4,18.4,'down',p);
  sprite(c,'listener',4.4,26.2,'down',p);sprite(c,'muse',2,23.4,'side',p);
  cat(c,9.6,19.6,p); // the critic's cat, on the desk papers
  deerhound(c,2.6,24.2,p,'right'); // the muse's deerhound at the window
  if(scene==='listening'){
    sprite(c,'roan',15.5,7,'down',p);sprite(c,'delta',24.5,7,'down',p);
    sprite(c,'evers',21.4,24.6,'up',p);
  }else{
    sprite(c,'evers',5,7,'up',p);sprite(c,'roan',15.5,7,'down',p);sprite(c,'delta',24.5,7,'down',p);
  }
}
export function drawWorld(cv,opts){
  opts=opts||{};const era=opts.era||'A',scene=opts.scene||'normal',dim=opts.dim==null?0.62:opts.dim;
  cv.width=W*T;cv.height=H*T;
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;
  const p=eraPal(era);
  paint(c,p,scene,era);
  if(scene==='listening'){
    c.fillStyle='rgba(7,9,13,'+dim+')';c.fillRect(0,0,cv.width,cv.height);
    c.save();c.beginPath();
    c.rect(14*T,15*T,18*T,18*T);       // archive + its walls
    c.rect(5*T,11*T,19*T,5*T);         // corridor path from Evers' door
    c.clip();paint(c,p,scene,era);c.restore();
    // walked path
    const path=[[6.5,12],[6.5,13.5],[22.5,13.5],[22.5,16],[22.2,21.5]];
    c.globalAlpha=0.5;
    for(let i=0;i<path.length-1;i++){const a=path[i],b=path[i+1];
      const n=Math.round(Math.hypot(b[0]-a[0],b[1]-a[1])*T/6);
      for(let k=0;k<n;k++)P(c,Math.round((a[0]+(b[0]-a[0])*k/n)*T),Math.round((a[1]+(b[1]-a[1])*k/n)*T),2,2,p.paperD);}
    c.globalAlpha=1;
    // sound rings off the platter
    ring(c,21*T+15,22*T+14,15,p.lamp,10);ring(c,21*T+15,22*T+14,22,p.lamp,14);ring(c,21*T+15,22*T+14,30,p.lamp,18);
  }
}
// ---- asset sheets
export const TILES=['floorboard','concrete','rug','wall','void+rain','console desk','tape rack','record shelf','turntable','crate','chair','armchair','lamp','window','dust ghost','puddle'];
export function drawTile(cv,id){
  const big=['console desk','tape rack','record shelf','turntable','armchair'].includes(id);
  cv.width=big?32:16;cv.height=big?32:16;
  cv.style.width=cv.width*3+'px';cv.style.height=cv.height*3+'px';
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;const p=PAL;
  P(c,0,0,cv.width,cv.height,id==='void+rain'?p.void:(id==='concrete'?p.conc:p.floor));
  if(id==='floorboard'){P(c,0,7,16,1,p.floorD);P(c,6,0,1,7,p.floorD);P(c,11,8,1,8,p.floorD);}
  if(id==='concrete'){P(c,0,0,16,16,p.conc);P(c,0,0,16,1,p.concD);P(c,3,8,5,1,p.concD);}
  if(id==='rug'){P(c,0,0,16,16,p.rug);P(c,4,4,2,2,p.rugD);P(c,10,10,2,2,p.rugD);P(c,0,0,1,16,p.rugD);}
  if(id==='wall'){P(c,0,0,16,16,p.wallCap);P(c,0,6,16,10,p.wallFace);P(c,0,5,16,1,p.ink);P(c,0,15,16,1,p.ink);}
  if(id==='void+rain'){P(c,3,2,1,4,p.rain);P(c,9,9,1,4,p.rain);}
  if(id==='console desk')consoleDesk(c,0,0.3,2,p,p.evers);
  if(id==='tape rack')reels(c,0,0.5,p);
  if(id==='record shelf')shelf(c,0,0.4,2,p);
  if(id==='turntable')turntable(c,0,0,p,true);
  if(id==='crate')crate(c,0,0,p);
  if(id==='chair')chair(c,0,0,p);
  if(id==='armchair')armchair(c,0.2,0.3,p);
  if(id==='lamp')lampPool(c,0,0,p);
  if(id==='window'){P(c,0,0,16,16,p.wallCap);windowV(c,-0.3,0,p);}
  if(id==='dust ghost')ghost(c,0.1,0.2,0.85,0.85,p);
  if(id==='puddle')puddle(c,0,0,p);
}
export function drawSheet(cv,who,scale){
  scale=scale||1;
  cv.width=3*18-2;cv.height=4*18-2;
  cv.style.width=cv.width*scale+'px';cv.style.height=cv.height*scale+'px';
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;
  const dk=dict(PAL,who),s=S[who];
  [['down',false],['side',false],['side',true],['up',false]].forEach(([dir,flip],r)=>{
    frames(s[dir]||s.down).forEach((m,f)=>drawMap(c,m,f*18,r*18,dk,flip));
  });
}
export function drawHero(cv,who,scale){
  scale=scale||6;cv.width=16;cv.height=16;
  cv.style.width=16*scale+'px';cv.style.height=16*scale+'px';
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;
  drawMap(c,S[who].down,0,0,dict(PAL,who));
}
export function drawDrift(cv){
  cv.width=4*20;cv.height=17;cv.style.width=cv.width*5+'px';cv.style.height=cv.height*5+'px';
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;
  const dk=dict(PAL,'roan');
  for(let set=0;set<4;set++){
    const m=S.roan.down.map((row,y)=>row.split('').map((ch,x)=>{
      if(ch==='.'||ch==='o')return ch;
      return ((x*31+y*17+set*53)%23<set*3)?'.':ch;
    }).join(''));
    drawMap(c,m,set*20+2,1,dk);
  }
}

// ---- THE STREET: AFAR house on the corner + Archive Row ----
const SW=56,SH=34;
export function streetGrid(){
  const g=Array.from({length:SH},()=>Array(SW).fill('V'));
  const fill=(x1,y1,x2,y2,t)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)g[y][x]=t;};
  fill(0,0,31,SH-1,'H');                 // AFAR house region, painted by paint()
  fill(32,2,33,32,'P');fill(38,2,39,32,'P'); // sidewalks
  fill(34,2,37,32,'D');                  // road
  const bld=(y1,y2,t)=>{fill(40,y1,53,y2,'W');fill(41,y1+1,52,y2-1,t);};
  bld(2,8,'L');bld(10,16,'F');bld(18,24,'F');bld(26,32,'L');
  g[13][40]='F';g[21][40]='F';           // resident doors onto the sidewalk
  g[5][40]='L';g[29][40]='L';            // lease doors, papered
  return g;
}
function windowW(c,tx,ty,p){P(c,tx*T+1,ty*T+1,5,14,p.ink);P(c,tx*T+2,ty*T+2,3,12,p.glass);P(c,tx*T+2,ty*T+8,3,1,p.ink);}
function paperWin(c,tx,ty,p){P(c,tx*T+1,ty*T+1,5,14,p.ink);P(c,tx*T+2,ty*T+2,3,12,p.paperD);P(c,tx*T+2,ty*T+5,3,1,p.ink);P(c,tx*T+2,ty*T+10,3,1,p.ink);}
function signPlate(c,tx,ty,p,col){P(c,tx*T+5,ty*T+4,7,9,p.ink);P(c,tx*T+6,ty*T+5,5,7,col);P(c,tx*T+7,ty*T+7,3,1,p.ink);P(c,tx*T+7,ty*T+9,3,1,p.ink);}
function amp(c,tx,ty,p){box(c,tx*T,ty*T,15,14,p.metalD,p.ink);disc(c,tx*T+7,ty*T+8,3,p.metal);P(c,tx*T+2,ty*T+2,11,2,p.metal);}
function bench(c,tx,ty,p){box(c,tx*T+1,ty*T+4,26,8,p.wood,p.ink);P(c,tx*T+2,ty*T+7,24,1,p.woodD);P(c,tx*T+3,ty*T+12,2,3,p.ink);P(c,tx*T+23,ty*T+12,2,3,p.ink);}
function mailbox(c,tx,ty,p){P(c,tx*T+7,ty*T+8,2,7,p.metalD);box(c,tx*T+4,ty*T+2,9,7,p.metal,p.ink);P(c,tx*T+5,ty*T+4,7,1,p.ink);P(c,tx*T+12,ty*T+1,1,4,p.evers);}
function dustPatch(c,tx,ty,p){c.globalAlpha=0.5;P(c,tx*T+3,ty*T+6,6,2,p.paperD);P(c,tx*T+8,ty*T+9,4,2,p.paperD);c.globalAlpha=1;}
function tree(c,tx,ty,p){
  P(c,tx*T+6,ty*T+10,4,8,'#3a2e1f');P(c,tx*T+5,ty*T+16,6,2,p.paveD); // trunk + pit
  const lv='#3f4a38',lvD='#333d2e',lvL='#4a5741';
  disc(c,tx*T+8,ty*T+2,8,lvD);disc(c,tx*T+8,ty*T+1,7,lv);
  disc(c,tx*T+5,ty*T-1,4,lvL);disc(c,tx*T+11,ty*T+3,3,lvD);
  P(c,tx*T+4,ty*T,2,2,lvL);P(c,tx*T+10,ty*T-3,2,2,lvL);
}
function car(c,tx,ty,p,col){
  // parked car, top-down, nose north, 2 tiles long
  box(c,tx*T+2,ty*T+1,12,30,col,p.ink);
  P(c,tx*T+4,ty*T+7,8,5,p.glass);P(c,tx*T+4,ty*T+21,8,4,p.glass); // windshield + rear
  P(c,tx*T+4,ty*T+13,8,7,shade2(col,0.12)); // roof
  P(c,tx*T+3,ty*T+2,2,2,p.paperD);P(c,tx*T+11,ty*T+2,2,2,p.paperD); // headlights
  P(c,tx*T+3,ty*T+28,2,2,p.eversD);P(c,tx*T+11,ty*T+28,2,2,p.eversD); // taillights
  P(c,tx*T+2,ty*T+5,1,4,p.ink);P(c,tx*T+13,ty*T+5,1,4,p.ink);P(c,tx*T+2,ty*T+23,1,4,p.ink);P(c,tx*T+13,ty*T+23,1,4,p.ink); // wheels
}
function shade2(hex,f){const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);const t=f<0?0:255,a=Math.abs(f);
  return 'rgb('+Math.round(r+(t-r)*a)+','+Math.round(g+(t-g)*a)+','+Math.round(b+(t-b)*a)+')';}
function subway(c,tx,ty,p){
  // NY subway stair entrance, 2x3 tiles: railed stairwell descending south
  P(c,tx*T,ty*T,2*T,3*T,p.pave);
  P(c,tx*T+2,ty*T+8,28,38,p.ink); // stair void
  for(let i=0;i<5;i++)P(c,tx*T+4,ty*T+10+i*7,24,3,shade2(p.asph,-(0.1+i*0.12))); // steps darkening down
  P(c,tx*T,ty*T+6,2,42,p.metalD);P(c,tx*T+30,ty*T+6,2,42,p.metalD); // railings
  P(c,tx*T,ty*T+6,32,2,p.metalD);
  // globe lamp on post (green = entrance)
  P(c,tx*T+30,ty*T-6,2,12,p.metalD);disc(c,tx*T+31,ty*T-8,3,'#3f4a38');P(c,tx*T+30,ty*T-9,1,1,'#4a5741');
  // R bullet sign on the rail head
  disc(c,tx*T+8,ty*T+3,5,'#e0b25a');ring(c,tx*T+8,ty*T+3,5,p.ink,30);
  P(c,tx*T+7,ty*T+1,1,5,p.ink);P(c,tx*T+8,ty*T+1,2,1,p.ink);P(c,tx*T+8,ty*T+3,2,1,p.ink);P(c,tx*T+10,ty*T+2,1,1,p.ink);P(c,tx*T+9,ty*T+4,1,2,p.ink); // pixel R
}
function deerhound(c,tx,ty,p,dir){
  // scottish deerhound: tall, wiry grey, long muzzle + tail. ~20x14 px
  const g1='#6a6f78',g2='#43474e',x=tx*T,y=ty*T,f=dir==='right';
  const X=(dx,dy,w,h,col)=>P(c,x+(f?20-dx-w:dx),y+dy,w,h,col);
  X(3,4,13,5,g1); // body
  X(3,3,13,1,g2); // wiry back
  X(14,1,4,4,g1);X(18,2,3,2,g1); // neck+head raised, long muzzle
  X(15,0,2,2,g2); // ear
  X(20,3,1,1,p.ink); // nose
  X(0,2,4,2,g2); // long tail low
  X(4,9,2,5,g1);X(8,9,2,5,g2);X(11,9,2,5,g1);X(14,9,2,5,g2); // long legs
  X(4,13,2,1,g2);X(14,13,2,1,g2);
  X(16,3,1,1,p.ink); // eye
}
function cat(c,tx,ty,p){
  // small ink cat, curled ~8x6
  const x=tx*T,y=ty*T;
  disc(c,x+4,y+4,3,p.ink);P(c,x+6,y+1,3,3,p.ink); // body + head
  P(c,x+6,y,1,1,p.ink);P(c,x+8,y,1,1,p.ink); // ears
  P(c,x+0,y+4,2,1,p.ink);P(c,x+1,y+3,1,1,p.ink); // tail wrap
  P(c,x+7,y+2,1,1,p.lamp); // one open eye
}
function lampPost(c,tx,ty,p){
  c.globalAlpha=0.12;disc(c,tx*T+8,ty*T+4,20,p.lamp);c.globalAlpha=0.25;disc(c,tx*T+8,ty*T+4,11,p.lamp);c.globalAlpha=1;
  P(c,tx*T+7,ty*T-8,2,12,p.metalD);P(c,tx*T+5,ty*T-11,6,4,p.ink);P(c,tx*T+6,ty*T-10,4,2,p.lamp);
}
function paintStreet(c,p,era,scene){
  paint(c,p,'normal',era);
  const g=streetGrid();
  for(let y=0;y<SH;y++)for(let x=32;x<SW;x++){
    const t=g[y][x],px=x*T,py=y*T;
    if(t==='V'){P(c,px,py,T,T,p.void);
      if(era!=='B'&&(x*13+y*29)%31<2){P(c,px+3,py+2,1,4,p.rain);P(c,px+9,py+9,1,4,p.rain);}
    }else if(t==='P'){P(c,px,py,T,T,p.pave);if(y%2===0)P(c,px,py,T,1,p.paveD);
      if((x*5+y*7)%11===0)P(c,px+4,py+9,4,1,p.paveD);
      if(g[y][x+1]==='D')P(c,px+14,py,2,T,p.curb);
      if(g[y][x-1]==='D')P(c,px,py,2,T,p.curb);
    }else if(t==='D'){P(c,px,py,T,T,p.asph);
      if((x*11+y*5)%13===0)P(c,px+3,py+6,6,1,p.asphD);
      if(x===35&&y%3!==2){c.globalAlpha=0.3;P(c,px+15,py+3,2,9,p.paperD);c.globalAlpha=1;}
    }else if(t==='W'){P(c,px,py,T,T,p.wallCap);
      const below=g[y+1]&&g[y+1][x];
      if(below&&below!=='W'&&below!=='V'&&below!=='H'){P(c,px,py+6,T,10,p.wallFace);P(c,px,py+15,T,1,p.ink);P(c,px,py+5,T,1,p.ink);}
    }else if(t==='L'){P(c,px,py,T,T,'#191b1f');if((x*7+y*3)%9===0)P(c,px+5,py+8,5,1,p.concD);
    }else if(t==='F'){P(c,px,py,T,T,p.floor);P(c,px,py+(y%2?7:15),T,1,p.floorD);P(c,px+((x*7+y*3)%3)*5+2,py,1,7,p.floorD);}
  }
  // AFAR street door: east wall, straight into the archive
  P(c,31*T,22*T,T,2*T,p.floor);P(c,31*T,22*T,2,2*T,p.woodD);P(c,31*T+14,22*T,2,2*T,p.woodD);
  // resident door thresholds
  [[40,13],[40,21]].forEach(([x,y])=>{P(c,x*T+1,y*T,2,T,p.woodD);P(c,x*T+13,y*T,2,T,p.woodD);});
  // lease doors, papered over + FOR LEASE sign plates
  [[40,5],[40,29]].forEach(([x,y])=>{P(c,x*T+3,y*T+2,10,12,p.paperD);P(c,x*T+4,y*T+4,8,1,p.ink);P(c,x*T+4,y*T+7,8,1,p.ink);});
  paperWin(c,40,3,p);paperWin(c,40,7,p);paperWin(c,40,27,p);paperWin(c,40,31,p);
  signPlate(c,40,4,p,p.paperD);signPlate(c,40,28,p,p.paperD);
  // resident windows to the street + name plates
  windowW(c,40,11,p);windowW(c,40,15,p);windowW(c,40,19,p);windowW(c,40,23,p);
  signPlate(c,40,12,p,p.paper);signPlate(c,40,20,p,p.paper);
  // RES 02 — move-in ready: dust ghosts where furniture will go
  ghost(c,44,12,2,1,p);ghost(c,48,13,1,1,p);
  // RES 03 — Vess Camber
  consoleDesk(c,43,19,2,p,p.guest);chair(c,45,20,p);amp(c,49,19,p);crate(c,51,22,p);papers(c,47,22,p);
  // street furniture
  bench(c,38,24,p);mailbox(c,32,20,p);
  // trees in sidewalk pits
  tree(c,32,5,p);tree(c,38,10,p);tree(c,32,29,p);tree(c,38,30,p);
  // R train entrance on the wide sidewalk, north end
  subway(c,38,4,p);
  // parked cars along the west curb
  car(c,34,8,p,'#4b4f57');car(c,34,17,p,'#5c4b37');car(c,34,25,p,'#43474e');
  if(era==='B'){dustPatch(c,35,6,p);dustPatch(c,36,30,p);}
  else{puddle(c,35,6,p);puddle(c,36,14,p);puddle(c,34,27,p);puddle(c,36,30,p);}
  lampPost(c,33,8,p);lampPost(c,38,16,p);lampPost(c,33,26,p);
  if(scene==='listening')sprite(c,'vess',35.5,21.4,'side',p);
  else sprite(c,'vess',44.4,20.6,'up',p);
}
export function drawStreet(cv,opts){
  opts=opts||{};const era=opts.era||'A',scene=opts.scene||'normal',dim=opts.dim==null?0.62:opts.dim;
  cv.width=SW*T;cv.height=SH*T;
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;
  const p=eraPal(era);
  paintStreet(c,p,era,scene);
  if(scene==='listening'){
    c.fillStyle='rgba(7,9,13,'+dim+')';c.fillRect(0,0,cv.width,cv.height);
    c.save();c.beginPath();
    c.rect(14*T,15*T,18*T,18*T);   // the archive, destination
    c.rect(31*T,19*T,9*T,6*T);     // the crossing
    c.rect(40*T,18*T,14*T,7*T);    // Vess's building, door left open
    c.clip();paintStreet(c,p,era,scene);c.restore();
    lampPost(c,33,8,p);lampPost(c,38,16,p);lampPost(c,33,26,p); // lamp pools stay lit
    const path=[[40.5,22],[36,22],[36,23.2],[31.6,23.2],[27,23.2],[23,22.3]];
    c.globalAlpha=0.5;
    for(let i=0;i<path.length-1;i++){const a=path[i],b=path[i+1];
      const n=Math.round(Math.hypot(b[0]-a[0],b[1]-a[1])*T/6)||1;
      for(let k=0;k<n;k++)P(c,Math.round((a[0]+(b[0]-a[0])*k/n)*T),Math.round((a[1]+(b[1]-a[1])*k/n)*T),2,2,p.paperD);}
    c.globalAlpha=1;
  }
}
export function drawResidentRoom(cv,opts){
  opts=opts||{};const acc=opts.acc||PAL.guest,accD=opts.accD||PAL.guestD,prop=opts.prop||'none',occ=!!opts.occupied;
  const W2=16,H2=11;cv.width=W2*T;cv.height=H2*T;
  const c=cv.getContext('2d');c.imageSmoothingEnabled=false;const p=PAL;
  for(let y=0;y<H2;y++)for(let x=0;x<W2;x++){
    const px=x*T,py=y*T,wall=x===0||x===W2-1||y===0||y===H2-1;
    if(wall){P(c,px,py,T,T,p.wallCap);if(y===0){P(c,px,py+6,T,10,p.wallFace);P(c,px,py+5,T,1,p.ink);P(c,px,py+15,T,1,p.ink);}}
    else{P(c,px,py,T,T,p.floor);P(c,px,py+(y%2?7:15),T,1,p.floorD);P(c,px+((x*7+y*3)%3)*5+2,py,1,7,p.floorD);}
  }
  windowW(c,0,3,p);windowW(c,0,6,p); // windows to the street — sightline to the corner
  P(c,7*T,(H2-1)*T,2*T,T,p.floor);P(c,7*T,(H2-1)*T,2,T,p.woodD);P(c,9*T-2,(H2-1)*T,2,T,p.woodD);
  consoleDesk(c,2,2,3,p,acc);chair(c,5,3,p);lampPool(c,11,3,p);
  ghost(c,10,6,3,3,p); // the character prop slot
  if(prop==='amp')amp(c,11,6.5,p);
  if(prop==='reels')reels(c,10.5,7,p);
  signPlate(c,14,0,p,occ?p.paper:p.paperD);
  if(occ){crate(c,13,8,p);papers(c,3,5,p);
    sprite(c,'vess',6,5,'down',Object.assign({},p,{guest:acc,guestD:accD}));}
}
