const BASE=[
'.....HHHHHH.....','....HHHHHHHH....','...HHHHHHHHHH...','...HHssssssHH...','...HsEssEssH....','....sssssss.....','.....ssMss......','......sss.......','....BBBBBBB.....','...BBDBBBDBB....','..ssBDDDDBBss...','..ssBBBBBBBss...','....BBBBBBB.....','.....DDDDD......','.....DD.DD......','....XXX.XXX.....'];
const colors=['#67baff','#ab7854','#f3cc55','#b187ff','#6bf0ad','#f38e99','#cdd9e9','#fb9864','#79c1aa','#bbabda','#e1c778','#7cdcea','#eacfa4'];
export function drawSprite(canvas,index,working=false,frame=0){const ctx=canvas.getContext('2d');ctx.clearRect(0,0,32,32);ctx.imageSmoothingEnabled=false;const palette={H:colors[index%colors.length],s:'#efc1a8',E:'#12151f',M:'#b46472',B:['#344d7e','#61403a','#645633','#473869'][index%4],D:'#91a1b4',X:'#242839'};
  const rows=BASE.map(x=>x);if(index===0||index===12)rows[4]='..XHsEssEssHX...';if(index===3)rows[6]='...HHssMssHH....';if(index===10)rows[1]='....XXXXXXXX....';
  rows.forEach((row,y)=>[...row].forEach((c,x)=>{if(c==='.')return;if(c==='E'&&!working&&frame===1)c='s';ctx.fillStyle=palette[c];ctx.fillRect(x*2,y*2+(working&&frame===1&&y>7?1:0),2,2);}));}
