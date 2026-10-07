const recent=new Map();
export function line(id,text){const choices=['자료 확인했어. ','내 검토 결과야. ','여기서 볼 부분은 이거야. '];let index=Math.floor(Math.random()*choices.length);if(index===recent.get(id))index=(index+1)%choices.length;recent.set(id,index);return choices[index]+text;}
