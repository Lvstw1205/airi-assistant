// Persistent textured mesh. Facial animation lives outside this canvas.
(()=>{
 function create(container,image){
  const canvas=document.createElement('canvas');canvas.className='character-mesh';canvas.setAttribute('aria-hidden','true');
  const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,antialias:true});if(!gl)return null;
  function shader(kind,code){const s=gl.createShader(kind);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
  const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,'attribute vec2 a_position;attribute vec2 a_uv;varying vec2 uv;void main(){uv=a_uv;gl_Position=vec4(a_position.x*2.-1.,1.-a_position.y*2.,0.,1.);}'));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float;varying vec2 uv;uniform sampler2D u_image;void main(){gl_FragColor=texture2D(u_image,uv);}'));gl.linkProgram(program);gl.useProgram(program);
  const grid=[],uvs=[],indices=[],cols=24,rows=28;
  for(let y=0;y<=rows;y++)for(let x=0;x<=cols;x++){grid.push([x/cols,y/rows]);uvs.push(x/cols,y/rows);}
  for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){const a=y*(cols+1)+x;indices.push(a,a+1,a+cols+1,a+1,a+cols+2,a+cols+1);}
  const vertices=new Float32Array(uvs.length),buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.DYNAMIC_DRAW);
  const position=gl.getAttribLocation(program,'a_position');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
  const uv=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uv);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(uvs),gl.STATIC_DRAW);const attribute=gl.getAttribLocation(program,'a_uv');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
  const index=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,index);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW);
  const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
  // Upload once. Blink/speech never changes the texture or its URL.
  gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);container.prepend(canvas);container.classList.add('mesh-ready');
  let values={angle:0,nod:0,breath:0,hair:0};
  const smooth=t=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
  function project(x,y){
   const head=1-smooth((y-.56)/.19),upper=1-smooth((y-.72)/.25),a=values.angle*head,dx=x-.53,dy=y-.64;
   let px=x+(Math.cos(a)*dx-Math.sin(a)*dy-dx)*head;
   let py=y+(Math.sin(a)*dx+Math.cos(a)*dy-dy)*head+values.nod*head;
   // Waist stays seated; torso, shoulders and forearms have independent weights.
   const torso=values.torso*upper,wx=px-.53,wy=py-.91;
   px+= (Math.cos(torso)*wx-Math.sin(torso)*wy-wx)*upper+values.lean*upper;
   py+= (Math.sin(torso)*wx+Math.cos(torso)*wy-wy)*upper+values.breath*upper;
   const shoulder=Math.exp(-(((y-.65)/.12)**2))*Math.exp(-(((Math.abs(x-.5)-.24)/.18)**2));
   py-=values.shoulder*shoulder;
   const forearm=Math.exp(-(((y-.78)/.12)**2))*Math.exp(-(((x-.31)/.17)**2));
   px+=values.arm*forearm;py-=values.arm*.35*forearm;
   px+=values.hair*Math.max(0,Math.abs(x-.5)-.22)*Math.sin(y*5)*upper;
   return [px,py];
  }
  function update(next){values=next;const ratio=Math.min(devicePixelRatio||1,1.5),w=Math.round(container.clientWidth*ratio),h=Math.round(container.clientHeight*ratio);if(!w||!h)return;
   if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
   for(let i=0;i<grid.length;i++){const p=project(...grid[i]);vertices[i*2]=p[0];vertices[i*2+1]=p[1];}
   gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,vertices);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawElements(gl.TRIANGLES,indices.length,gl.UNSIGNED_SHORT,0);
  }
  return {update,project,canvas};
 }
 window.AIRICharacterMesh={create};
})();
