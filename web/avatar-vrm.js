import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

function validate(buffer){
  if(buffer.byteLength<20||buffer.byteLength>40*1024*1024)throw Error('40MB 이하의 VRM 파일이 필요합니다.');
  const view=new DataView(buffer);
  if(view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2||view.getUint32(8,true)!==buffer.byteLength||view.getUint32(16,true)!==0x4e4f534a)throw Error('유효한 VRM/GLB 파일이 아닙니다.');
  const doc=JSON.parse(new TextDecoder().decode(buffer.slice(20,20+view.getUint32(12,true))));
  if(!doc.extensions?.VRM&&!doc.extensions?.VRMC_vrm)throw Error('VRM 리깅 정보가 없습니다.');
  for(const resource of [...doc.buffers||[],...doc.images||[]])if(resource.uri&&!resource.uri.startsWith('data:'))throw Error('외부 텍스처가 없는 VRM을 선택하세요.');
}

export async function createAvatar(buffer,host){
  validate(buffer);
  const manager=new THREE.LoadingManager();
  manager.setURLModifier(url=>{if(url.startsWith('blob:')||url.startsWith('data:'))return url;throw Error('외부 파일 요청을 허용하지 않습니다.');});
  const loader=new GLTFLoader(manager);loader.register(parser=>new VRMLoaderPlugin(parser));
  const gltf=await loader.parseAsync(buffer,'');const vrm=gltf.userData.vrm;
  if(!vrm?.humanoid){VRMUtils.deepDispose(gltf.scene);throw Error('캐릭터의 뼈대를 읽지 못했습니다.');}
  VRMUtils.rotateVRM0(vrm);
  let vertices=0;vrm.scene.traverse(node=>{if(node.geometry)vertices+=node.geometry.attributes.position?.count||0;});
  if(vertices>1000000){VRMUtils.deepDispose(vrm.scene);throw Error('이 Mac에서 표시하기에 모델이 너무 복잡합니다.');}
  let renderer;
  try{renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'});}
  catch(e){VRMUtils.deepDispose(vrm.scene);throw Error('이 브라우저에서 3D 렌더링을 시작하지 못했습니다. 기본 얼굴을 유지합니다.');}
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.domElement.className='vrm-canvas';renderer.domElement.style.removeProperty('display');renderer.domElement.setAttribute('aria-label','AIRI 3D 캐릭터');host.append(renderer.domElement);
  const scene=new THREE.Scene();scene.add(vrm.scene,new THREE.HemisphereLight(0xd8ffff,0x282737,2.5));
  const light=new THREE.DirectionalLight(0xffffff,2.2);light.position.set(1,2,3);scene.add(light);
  vrm.scene.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(vrm.scene),height=bounds.max.y-bounds.min.y;
  const head=vrm.humanoid.getNormalizedBoneNode('head'),neck=vrm.humanoid.getNormalizedBoneNode('neck');
  const target=new THREE.Vector3();(head||vrm.scene).getWorldPosition(target);target.y+=height*.035;
  const camera=new THREE.PerspectiveCamera(30,1,.01,100);camera.position.copy(target);camera.position.z+=Math.max(.5,height*.34/(2*Math.tan(Math.PI/12)));camera.lookAt(target);
  const headRest=head?.rotation.clone(),neckRest=neck?.rotation.clone(),rootY=vrm.scene.position.y;
  const resize=new ResizeObserver(()=>{const size=Math.max(1,host.clientWidth);renderer.setSize(size,size,false);});resize.observe(host);
  let disposed=false;
  return {
    expressions:!!vrm.expressionManager,
    update(delta,motion){
      if(disposed)return;
      if(head){head.rotation.x=headRest.x+motion.pitch;head.rotation.y=headRest.y+motion.yaw;head.rotation.z=headRest.z+motion.roll;}
      if(neck)neck.rotation.z=neckRest.z+motion.roll*.25;
      vrm.scene.position.y=rootY+motion.breathe*height*.003;
      const expressions=vrm.expressionManager;
      if(expressions){expressions.setValue('blink',motion.blink);expressions.setValue('aa',motion.mouth*.8);expressions.setValue('ou',motion.mouth*.2);expressions.setValue('happy',motion.smile*.25);}
      vrm.update(delta);renderer.render(scene,camera);
    },
    dispose(){disposed=true;resize.disconnect();VRMUtils.deepDispose(vrm.scene);renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();}
  };
}
