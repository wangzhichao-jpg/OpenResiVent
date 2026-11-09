import { cloneCase, shaftRun } from './cases'
const shaft=cloneCase('shaft')
console.log(JSON.stringify({ventilation:cloneCase('ventilation'), dwelling:cloneCase('dwelling'), shaft:shaftRun(shaft)}))
