/* Select supplied still poses from context; never change the office or use video. */
(()=>{
 const rules=[
  ['stretch2',/팔.*(?:뻗|올려)|기지개|stretch.*(?:arms|up)|étire.*bras/i],
  ['stretch',/스트레칭|몸.*풀|stretch|étirement/i],
  ['sleepy',/잘\s*자|졸려|졸린|졸립|잠.*자|good\s*night|sleepy|bonne nuit|sommeil/i],
  ['tired',/피곤|지쳤|쉬자|휴식|tired|exhausted|take a break|fatigu/i],
  ['aegyo',/애교|aegyo|act.*sweet/i],
  ['cute',/하트|귀여|cute|heart|mignon/i],
  ['swagger',/자신감|당당|뿌듯|성공했|swagger|confident|nailed it|fier/i],
  ['angry',/화난.*(?:표정|모습)|화내.*(?:봐|줘)|angry pose|look angry|fâchée/i],
  ['panic',/놀란.*(?:표정|모습)|깜짝|당황|surpris|panic|oh no/i],
  ['sad',/슬퍼|슬픈|속상|위로|sad|upset|triste/i],
  ['happy',/고마|잘했|축하|기뻐|농담|웃어|happy|thank|congrat|joke|merci|bravo/i],
  ['focus',/분석|조사|검색|공부|학습|집중|실적|주가|경제|research|analy|study|focus|stock|économie|étudi/i],
  ['idle',/평소.*(?:자세|모습)|기본.*자세|neutral|normal pose/i]
 ];
 window.AIRIGesturePolicy={forText(text){return rules.find(([,pattern])=>pattern.test(text||''))?.[0]||null;},rules:rules.map(([name])=>name)};
})();
