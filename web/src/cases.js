import YAML from 'yaml'
import ventilation from '../../cases/book/ch02/ex2-03.yaml?raw'
import dwelling from '../../cases/book/ch05/ex5-07.yaml?raw'
import shaftReport from '../../cases/reports/shaft_example.yaml?raw'
import commissioning from '../../cases/reports/commissioning_example.yaml?raw'

export const examples = { ventilation: YAML.parse(ventilation), dwelling: YAML.parse(dwelling), shaft: YAML.parse(shaftReport), commissioning: YAML.parse(commissioning) }
export function cloneCase(kind) { return structuredClone(examples[kind]) }
export function exampleNoise() { return {reference_flow_m3_s:100/3600,flows_m3_s:[50/3600,75/3600,100/3600],fan_power_db:[60,62,64,62,58,53,48,42],flow_exponent:5,stages:[{kind:'straight',attenuation_db:[1,2,3,4,5,6,7,8],regenerated_db:[32,34,36,38,37,34,30,25]},{kind:'bend',attenuation_db:[1,2,3,4,5,5,4,3],regenerated_db:[30,32,35,38,38,35,32,27]},{kind:'silencer',attenuation_db:[3,5,8,12,15,16,14,10],regenerated_db:[28,30,33,35,36,34,30,25]}],terminal_reflection_db:[6,5,4,3,2,1,1,1],diffuser_regenerated_db:[25,28,31,34,35,33,30,25],directivity:2,distance_m:2,room_constant_m2:20,target_db:33,target_kind:'GB 55016-2021 第2.1.4条表2.1.4 睡眠空间设备声'} }
export function shaftRun(data) { return { meta: { id: 'shaft-model', title: '竖井计算', rules: [] }, module: 'shaft', input: structuredClone(data.input.shaft), output: {} } }
export function parseCase(text) { const v = YAML.parse(text); if (!v || typeof v !== 'object' || !v.module || !v.input || !v.meta) throw new Error('算例须包含 meta、module、input'); return v }
export function encodeCase(value, format) { return format === 'yaml' ? YAML.stringify(value) : JSON.stringify(value, null, 2) }

const parameterNames = { area_m2:'面积', floor_area_m2:'建筑面积', height_m:'净高', occupants:'人数', outdoor_ppm:'室外二氧化碳浓度', limit_ppm:'浓度限值', allowance:'风量附加率', hcho_sensitivity:'甲醛敏感性系数', bedrooms:'卧室', living:'起居室', activity:'活动类型', hcho_materials:'装修材料', ef_mg_m2_h:'单位面积散发率', source:'原始来源说明', volume_m3:'住宅体积', n50_per_h:'气密性', kitchen_open:'开敞式厨房', door_gap_area_m2:'门缝面积', transfer_area_m2:'过流面积', density_kg_m3:'空气密度', hood_m3_h:'油烟机风量', fresh_supply_m3_h:'新风送风量', fresh_exhaust_m3_h:'新风排风量', opening_area_m2:'补风口面积', mechanical_makeup_m3_h:'机械补风量', hood_room:'油烟机位置', supply_room:'送风位置', exhaust_room:'排风位置', bath_fan_room:'卫生间风机位置', threshold_pa:'压差提示阈值', shaft:'竖井', dwelling:'户内', floors:'楼层数', fraction:'使用率', distribution:'运行分布', inside_temperature:'室内温度', outside_temperature:'室外温度', width:'竖井宽度', depth:'竖井深度', fan_kind:'风机类型', valve_class:'止回阀等级', floor_height:'层高', roughness:'粗糙度', branch_diameter:'支管直径', branch_length:'支管长度', branch_local_loss:'支管局部阻力系数', valve_diameter:'止回阀直径', valve_forward_cd:'止回阀正向流量系数', seed:'随机种子', roof_discharge:'屋顶出口流量系数', roof_area:'屋顶出口面积', wind_speed:'风速', roof_cp:'屋顶风压系数', dwelling_volume:'住宅容积', n50_per_s:'每秒气密性', exponent:'泄漏指数' }
Object.assign(parameterNames,{noise:'噪声',reference_flow_m3_s:'参考风量',flows_m3_s:'运行风量',fan_power_db:'风机声功率',flow_exponent:'风量指数',stages:'风管元件',kind:'元件类型',attenuation_db:'衰减',regenerated_db:'再生声功率',terminal_reflection_db:'末端反射损失',diffuser_regenerated_db:'风口再生声',directivity:'指向因子',distance_m:'测点距离',room_constant_m2:'房间常数',target_db:'目标声级',target_kind:'目标来源'})
const displayPath = path => path.replace(/[A-Za-z_][A-Za-z_0-9]*/g, key => parameterNames[key] || '其他参数')
export function parameterSources(kind, value) {
  const base={...(examples[kind]?.input ?? {})}
  if(kind==='ventilation' && value?.input?.noise) base.noise=exampleNoise()
  const rows=[]
  const walk=(v, b, path) => {
    if (Array.isArray(v)) return v.forEach((x,i)=>walk(x,Array.isArray(b)?b[i]:undefined,`${path}[${i+1}]`))
    if (v && typeof v === 'object') return Object.entries(v).forEach(([k,x])=>walk(x,b && typeof b==='object'?b[k]:undefined,path?`${path}.${k}`:k))
    const values={sleeping:'睡眠',sedentary:'久坐',uniform:'均匀',lower:'低层',upper:'高层',random:'随机',ordinary:'普通',common:'标准',high:'高静压',good:'良好',medium:'中等',poor:'较差',living:'起居室',kitchen:'厨房',bath:'卫生间',bed1:'卧室一',straight:'直管',bend:'弯头',silencer:'消声器'}
    rows.push({parameter:displayPath(path),value:typeof v==='boolean'?(v?'是':'否'):(values[v] ?? String(v)),source:JSON.stringify(v)===JSON.stringify(b)?'假设，需作者确认':'用户输入'})
  }
  walk(value?.input,base,'')
  if(kind==='shaft') {
    const defaults={floors:6,floor_height:3,width:0.5,depth:0.4,roughness:0.00015,branch_diameter:0.2,branch_length:1,branch_local_loss:1,valve_diameter:0.2,valve_forward_cd:0.6,valve_class:'中等',fan_kind:'普通',fraction:1,distribution:'均匀',seed:0,inside_temperature:293.15,outside_temperature:293.15,roof_discharge:0.6,roof_area:0.2,wind_speed:0,roof_cp:0,dwelling_volume:250,n50_per_s:1/3600,exponent:0.65}
    for(const [key,val] of Object.entries(defaults)) if(!(key in value.input.shaft)) rows.push({parameter:`竖井.${parameterNames[key]}`,value:String(val),source:'通用参数（模型默认，需确认）'})
  }
  rows.push({parameter:'计算方法及规则包',value:'依据算例选择',source:'通用参数'})
  return rows
}
