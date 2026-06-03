import type { ParamDef } from '../types'

export const GROUP_RULES: { name: string; keywords: string[] }[] = [
  {
    name: '输入输出',
    keywords: [
      'input', 'output', 'of', 'format', 'input_layer', 'output_layer',
      'output_dir', 'source', 'dest', 'in', 'out',
    ],
  },
  {
    name: '坐标系设置',
    keywords: ['s_srs', 't_srs', 'srs', 'crs', 'rpc', 'geoloc', 'a_srs'],
  },
  {
    name: '变换选项',
    keywords: [
      'resampling', 'xres', 'yres', 'order', 'et', 'te', 'ts', 'tr', 'tap',
      'wo', 'ot', 'scale', 'outsize',
    ],
  },
  {
    name: '裁剪与范围',
    keywords: [
      'cutline', 'crop_to_cutline', 'projwin', 'srcwin', 'extent',
      'clip', 'bbox',
    ],
  },
  {
    name: '栅格选项',
    keywords: [
      'band', 'bands', 'srcband', 'dstband', 'burn', 'add_alpha', 'rgba',
      'combine_bands', 'color_map', 'palette_file', 'color_interpretation',
      'color_selection', 'band_count', 'zones_band', 'weights_band',
    ],
  },
  {
    name: '图层设置',
    keywords: [
      'layer', 'nln', 'active_layer', 'layer_name', 'lyr_name',
      'method_layer', 'like_layer', 'zones_layer', 'layer_only',
      'no_create_empty_layers',
    ],
  },
  {
    name: '高级选项',
    keywords: [
      'overwrite', 'quiet', 'multi', 'dstalpha', 'update', 'append',
      'upsert', 'skip_errors', 'processes', 'nodata', 'mask',
      'creation_option', 'layer_creation_option',
    ],
  },
]

export const FALLBACK_GROUP = '其他选项'

/** GDAL 标准缩写：精确匹配，避免与 command/config 等误匹配 */
const GDAL_SHORTHANDS: Record<string, string> = {
  co: '高级选项',
  lco: '高级选项',
  dsco: '高级选项',
}

/** 按参数名推断所属分组 */
export function inferParamGroup(paramName: string): string {
  const lower = paramName.toLowerCase()

  // 优先处理 GDAL 标准缩写（精确匹配，避免 includes 误匹配）
  if (lower in GDAL_SHORTHANDS) {
    return GDAL_SHORTHANDS[lower]
  }

  for (const rule of GROUP_RULES) {
    if (rule.keywords.some((k) => lower === k || lower.includes(k))) {
      return rule.name
    }
  }
  return FALLBACK_GROUP
}

/** 将参数列表按分组聚合，保持原始顺序 */
export function groupParams(params: ParamDef[]): Map<string, ParamDef[]> {
  const map = new Map<string, ParamDef[]>()
  for (const p of params) {
    const group = inferParamGroup(p.name)
    if (!map.has(group)) map.set(group, [])
    map.get(group)!.push(p)
  }
  return map
}

/** 分组排序：有必填参数的组排前面，"其他选项"排最后 */
export function sortGroups(
  grouped: Map<string, ParamDef[]>,
): [string, ParamDef[]][] {
  const entries = Array.from(grouped.entries())
  return entries.sort((a, b) => {
    const aHasReq = a[1].some((p) => p.required)
    const bHasReq = b[1].some((p) => p.required)
    if (aHasReq && !bHasReq) return -1
    if (!aHasReq && bHasReq) return 1
    if (a[0] === FALLBACK_GROUP) return 1
    if (b[0] === FALLBACK_GROUP) return -1
    return 0
  })
}
