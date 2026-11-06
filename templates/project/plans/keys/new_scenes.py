"""E02–E20 用到、主场景库里没有的一次性场景。写法同 assets_spec/scenes.py：en 只写外观（不出现可读文字），layout 固定方位，light 唯一光线逻辑。"""
S = {
 'D-FRANKST': dict(name_en='Franklin Street in the morning', cn='Franklin St 街景（晨）',
  en=("a quiet cobbled lower-Manhattan street of nineteenth-century cast-iron loft buildings with tall arched windows and fire escapes, the building at frame-left with a wide dark green door at street level and three stone steps, "
      "wet dark asphalt with puddles after rain, an old iron lamppost at the curb, a few parked cars far down the block, a steam-vented manhole, the sky gray-white and clearing at the end of the street"),
  layout="Layout, fixed in every shot: the green door and stone steps are at frame-left; the street runs away from the camera toward the far end at frame-center; the lamppost is at the curb at frame-right.",
  light="soft gray-white morning overcast with a thin warm gleam on the wet street, puddles mirroring the cast-iron facades"),
}
