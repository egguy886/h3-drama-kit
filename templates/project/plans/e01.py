"""E01 示例（2 段）：演示工具包推荐写法——会动的开场全景、状态先行、前景失焦、眼神写法、有动机的运镜、同场景硬切换景别 + 切点动机。
运行：python3 plans/e01.py && python3 tools/compose_plan.py E01 && python3 tools/build_episode.py episodes/E01 --voices voices.json"""
from pw import *

MIA, LEO, ROOF, PHONE = "C01", "C02", "N-ROOFTOP", "P01"
BLK = ("the stair hut with its closed grey door stands at frame-left; the parapet and the city skyline run along frame-right.",
       "楼梯间和灰门在画左；矮墙与城市天际线沿画右。")   # 站位卡只写整段不动的东西；会走动的人写进镜头
MOOD = ("Two people who keep finding each other in the rain.", "两个总在雨里找到彼此的人。")
S = []
S.append(seg(1, "场01 雨夜天台：Leo 推门进雨里，Mia 背对着他", ROOF, "night_neon", "A", "HARD_CUT", [MIA, LEO], None,
  "The target video opens at {N-ROOFTOP} in heavy rain: {C02} steps out of the stair hut and calls across to {C01}, who stands at the parapet with her back to him; she answers without turning, her thumb on {P01}.",
  "Steady rain on concrete, a door creaking open, distant traffic far below, a buzzing neon sign; the ambience dips under each spoken line.",
  ("对白段。", "雨夜天台，Leo 推开楼梯间的门走进雨里，Mia 已经站在矮墙边背对着他；他隔着雨跟她说话，她不回头地回答，拇指在手机边缘蹭了一下。", "她在躲，他在找。", "雨打水泥地、门轴吱呀、远处车流、霓虹灯嗡嗡声，台词时压低。", "红色霓虹在湿地上的倒影是全集母题。"),
  [sh(2.2, "全景（缓推）：雨夜天台，灰门推开，Leo 走进雨里；Mia 已在画右矮墙边背对他",
      "the camera opens on a wide shot of {N-ROOFTOP} and pushes in slowly through the rain as the grey stair-hut door at frame-left swings open and {C02} comes out into the downpour, {C01} already standing at the parapet at frame-right with her back to him.",
      "全景，镜头冒雨缓推：画左楼梯间的灰门被推开，Leo 走进大雨；Mia 早已站在画右矮墙边，背对着他。"),
   sh(3.8, "Leo 中近景（前景虚化的栏杆，缓推）：隔着雨望向画右的 Mia，说 L1",
      "the camera cuts to a medium close-up of Leo framed through a soft out-of-focus foreground of a rain-streaked railing, the camera pushing in slowly as he squints through the rain, his eyes on Mia at frame-right, a crooked half-smile. {SAY:C02} amused and tired, says: {{d:L1}}",
      "Leo 中近景，前景是虚化的带雨栏杆，镜头缓推：他眯眼隔着雨，目光落在画右的 Mia 身上，嘴角歪着笑，带点疲惫地说：{{q:L1}}", "L1"),
   sh(2.8, "Mia 近景（霓虹红光）：眼睛先看向画左的 Leo，头不动，说 L2",
      "the camera cuts to a close-up of Mia at the parapet, red neon light on her wet face, her eyes sliding left toward Leo a beat before her head stays still. {SAY:C01} flat and dry, says: {{d:L2}}",
      "Mia 近景，霓虹红光打在她湿漉漉的脸上：眼睛先往画左瞟向 Leo，头保持不动，平淡干脆地说：{{q:L2}}", "L2"),
   sh(1.4, "极特写：手机空白屏亮着，她拇指蹭一下边缘停住",
      "the camera cuts to an extreme close-up of {P01} in Mia's hand, rain beading on the blank glowing screen as {ACT:Mia:thumb}.",
      "极特写：Mia 手里的手机，雨珠落在空白发亮的屏幕上，她的拇指在边缘蹭了一下停住。"),
   sh(2.4, "过肩（Mia 肩后，横移）：Leo 冒雨朝矮墙走近",
      "the camera cuts to an over-the-shoulder shot from behind Mia's shoulder at frame-right, the camera trucking left as Leo walks toward the parapet through the rain, his eyes on the back of her head.",
      "过肩，从 Mia 画右的肩后，镜头横移：Leo 冒雨朝矮墙走来，眼睛盯着她的后脑。"),
   sh(2.4, "Leo 中景（手持跟拍）：停在她身后一步远，雨水顺着脸往下淌",
      "the camera cuts to a handheld medium shot that tracks with Leo toward frame-right as he stops one step behind Mia, rain running down his face, his gaze fixed on her shoulder.",
      "Leo 中景，手持朝画右跟拍：他停在 Mia 身后一步远，雨水顺着脸往下淌，目光落在她肩上。")],
  props=[PHONE], blocking=BLK, mood=MOOD, seam_motive="gaze", transition={"type": "cut", "note": "Leo 盯着她的肩 → 下一段从她的脸开始（视线接续）"}))
S.append(seg(2, "场01 雨夜天台：Leo 追问，Mia 终于看他；两人并肩", ROOF, "night_neon", "A", "（集尾）", [MIA, LEO], None,
  "The target video continues at {N-ROOFTOP}: {C02} asks why he always finds her; {C01} finally turns and tells him it is because she lets him; they stand side by side at the parapet as the city glitters in the rain.",
  "Steady rain, a soft exhale, the buzz of the neon sign, the city humming far below; the ambience dips under each spoken line.",
  ("对白段。", "Leo 追问为什么自己总能找到她；Mia 终于转身看他，说是因为她愿意被找到；两人并肩站在矮墙边，城市灯火在雨里铺开。", "防线松开了一寸。", "雨声、一口轻轻的呼气、霓虹嗡嗡声、远处城市的低鸣，台词时压低。", "两人第一次并排入画。"),
  [sh(2.2, "Mia 近景（缓推）：雨里的侧脸，她听见身后的脚步停下",
      "the camera opens on a close-up of Mia's profile in the rain and pushes in slowly, red neon on her cheek, her eyes on the city lights below, wary, her jaw tight and her breath held as the footsteps behind her stop.",
      "Mia 近景，镜头缓推：雨里的侧脸，霓虹红光落在脸颊上，她望着脚下的城市灯火，警觉，下颌绷紧、屏住呼吸，身后的脚步停下了。"),
   sh(3.4, "Leo 近景（前景虚化的雨滴）：看着她的侧脸，说 L3",
      "the camera cuts to a close-up of Leo framed through soft out-of-focus raindrops in the foreground, his eyes on the side of Mia's face. {SAY:C02} quiet and steady, says: {{d:L3}}",
      "Leo 近景，前景是虚化的雨滴：他看着 Mia 的侧脸，低声而平稳地说：{{q:L3}}", "L3"),
   sh(2.4, "Mia 近景：转过头，眼睛先对上他，说 L4",
      "the camera cuts to a close-up of Mia as her eyes reach Leo first and her head follows, a small crack of a smile. {SAY:C01} soft and certain, says: {{d:L4}}",
      "Mia 近景：她转过来，眼睛先对上 Leo，头随后跟上，嘴角裂开一点笑，轻而笃定地说：{{q:L4}}", "L4"),
   sh(1.6, "极特写：她按灭手机屏幕，揣进夹克口袋",
      "the camera cuts to an extreme close-up as Mia's thumb presses the side of {P01}, the glowing screen goes dark and the phone slides into her jacket pocket.",
      "极特写：Mia 的拇指按下手机侧键，发亮的屏幕暗下去，手机滑进夹克口袋。"),
   sh(2.8, "双人中景（横移）：两人并肩站在矮墙边",
      "the camera cuts to a medium two-shot as the camera trucks right along the parapet, Leo stepping up beside Mia so they stand shoulder to shoulder at the wall, the rain easing around them.",
      "双人中景，镜头横移：Leo 走到 Mia 身边，两人肩并肩站在矮墙前，雨势在他们周围变小。"),
   sh(2.6, "全景（缓拉）：两人背影站在天台边，城市灯火铺开",
      "the camera cuts to a wide shot behind them and pulls back slowly, the two small figures standing together at the parapet against the glittering city, the red neon sign glowing on the far corner.",
      "全景，镜头缓拉：两人小小的背影并肩站在天台边，面前是铺开的城市灯火，远角的红色霓虹亮着。")],
  props=[PHONE], blocking=BLK, mood=MOOD))
write("E01", "示例集", header=["示例：工具包推荐写法演示"], notes=[], segs=S)
