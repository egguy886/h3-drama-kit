"""每段的首帧站位（学自 Higgsfield 的 LOCATION AND FIRST FRAME）：每段 15 秒单独生成，模型看不到上一段，
所以要写清 0.0 秒时：每个人在场景的哪个位置、画面哪一侧、什么姿势（站/坐/躺/跪）、朝向、手里拿着什么；必要时写机位（在哪、多高、朝哪看）。
同场景接缝段 = 上一段最后一个画面的状态；写成肯定句，别写否定词。pw.write() 会把它并进 plan_src 的 start 字段，compose 写进 subject_definitions 末尾。
格式：STARTS["E34"][2] = ("英文", "中文")
"""
STARTS = {}

# 例：
# STARTS["E01"] = {
#     2: ("Mia lies on her back in the middle of the bed, her hair spread on the pillow; Leo kneels over her, braced on both arms; the bedside lamp glows at frame-right.",
#         "Mia 仰躺在床中间、头发散在枕上；Leo 跪在她上方双臂撑着；右侧床头灯亮着。"),
# }
