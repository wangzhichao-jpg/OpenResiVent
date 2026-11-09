import { exampleDefinition, baseCase, makeDraft, buildDefinition } from './sweep'
const output={}
for (const kind of ['shaft','makeup']) {
  const spec=exampleDefinition(kind)
  const draft=makeDraft(spec)
  for(const row of draft) row.text=JSON.stringify(JSON.parse(row.text).slice(0,row===draft[0]?2:1))
  output[kind]={spec:buildDefinition(spec,draft,Object.keys(spec.metrics),'factorial',42,20),case:baseCase(kind)}
}
console.log(JSON.stringify(output))
