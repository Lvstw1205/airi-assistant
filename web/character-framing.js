/* A shared head anchor, fitted inside the character's grid cell, for raster
   and video sources with different camera distances. Never stretch aspect ratios. */
(()=>{
 const portraits={hardworking:[.52,.23,.47],focus:[.46,.23,.49],happy:[.48,.23,.50],idle:[.47,.24,.50],angry:[.53,.23,.48],aegyo:[.44,.24,.51],cute:[.44,.24,.52],panic:[.52,.23,.54],sad:[.48,.28,.48],sleepy:[.46,.30,.52],stretch:[.5,.45,.37],stretch2:[.5,.45,.37],swagger:[.46,.26,.50],tired:[.44,.25,.51]};
 const videos={hardworking:[.51,.28,.27],focus:[.50,.28,.27],happy:[.47,.30,.32],sleepy:[.49,.31,.29],stretch:[.50,.30,.23],stretch2:[.5,.36,.36]};
 window.AIRIFraming={fit(element,host,{width,height,name,video=false,bounds=[0,0,1,1]}){
  const [cx,cy,hw]=(video?videos:portraits)[name]||[.5,.25,.5],w=host.clientWidth,h=host.clientHeight;
  if(!w||!h)return;
  const [bx,by,bw,bh]=bounds,iw=width*bw,ih=height*bh;
  const scale=Math.min(h*.40/(width*hw),w*.98/iw,h*.98/ih);
  const dw=iw*scale,dh=ih*scale;
  const left=Math.max(0,Math.min(w-dw,w*.5-(cx-bx)*width*scale));
  const top=h-dh;
  Object.assign(element.style,{width:dw+'px',height:dh+'px',left:left+'px',top:top+'px',right:'auto',bottom:'auto'});
 }};
})();
