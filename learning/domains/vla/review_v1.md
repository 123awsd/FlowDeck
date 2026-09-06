# VLA Curriculum v1 — Independent Reverse Review

> 审查日期：2026-09-06
> 被审对象：VLA Curriculum v1 工作初稿
> 最终结果：39 节点；P0=15、P1=21、P2=3；foundation=19、evolving=17、frontier=3

## 1. 初稿存在的问题

工作初稿的候选池一度超过 40 个节点。主要问题不是“知识不够”，而是**范围过宽、热点过度独立成节点、P0 过多、术语边界混乱**：

- 把通用 MDP/robot control fundamentals 单列为 VLA P0，重复了学习者已有背景，也会把课程扩张成 Robot Learning 课程。
- action generation 中把“parallel/hybrid decoding”独立成节点，和 AR/diffusion/flow、dual-system 的边界不清。
- 把 safety、failure detection、recovery 拆成多个节点，证据和工程接口高度重叠，容易膨胀成机器人安全课程。
- 3D perception、tactile/force、audio 分得过细，而它们并非所有 VLA 的共同必要条件。
- long-horizon memory 被作为独立 P1，但现有 VLA survey 更常把它列为 future direction，证据成熟度不足。
- World Model 一度被赋予过大的课程范围，和独立的 world-model curriculum 冲突。
- P0 候选接近半数以上，无法体现真正“最低论文阅读闭环”。

## 2. 发现的遗漏

反向检查 Survey、课程和 curated repo 后，确认初稿必须补强/显式化以下方向：

1. **动作 token 术语消歧。** Action Tokenization Survey 的“action token”是广义链条概念，而 RT-2/OpenVLA 工程语境常指离散低层动作；必须拆开。
2. **连续 action decoding。** 如果只讲 AR/diffusion/flow，会遗漏直接 regression/action head 这个共同基线和接口。
3. **机器人 state/proprioception。** 只讲 vision+language 会造成“VLA 输入只有 RGB+text”的错误印象。
4. **trajectory schema 与时间对齐。** 数据模块不能只列数据集名，必须包含 episode/state/action/action convention 这一工程底座。
5. **真实部署的 control Hz 与 latency budget。** 模型 FPS 不等于 robot control frequency。
6. **跨本体 action alignment。** 不能把“多机器人训练”简化成 dataset mixture；不同 DoF/坐标/频率是独立核心问题。
7. **评测可比性。** 不能只记 benchmark 名，必须把 seen/unseen、trial protocol、真实/仿真和 success 判定作为节点目标。

这些遗漏已进入最终 v1，而不是只留在建议中。

## 3. 删除或合并了哪些节点

最终实际执行了以下删改：

- **删除** `mdp_and_robot_control_interface` 候选节点：只把必要控制/MDP语义嵌入 VLA 问题定义、action space 和 RL post-training，不单独开泛机器人基础课。
- **合并** `parallel_action_decoding` / `hybrid_action_decoding`：不再独立占节点；相关内容进入 AR/diffusion/flow 比较、dual-system/action expert 和 inference scope。
- **合并** `safety_alignment`、`failure_detection`、`failure_recovery` 为 `failure_modes_and_reliability`：保留 VLA 直接相关的 detection/replan/recovery/safety 接口，拒绝泛安全扩张。
- **合并** `three_d_perception`、`tactile_force_modalities`、`audio_conditioning` 为 `extended_modalities_3d_tactile_audio`，并降为 P2/frontier。
- **取消独立** `long_horizon_memory`：短期 temporal context 保留在 `temporal_context_and_observation_history`；长期 memory 只作为 reasoning/world-model 未来更新信号。
- **收窄** 原广义 `world_models` 为 `world_model_vla_interface`，明确不教授完整 World Model。
- **拆分术语**：把原本含混的 `action_tokens` 拆为 `action_discretization_and_tokenization` 与 `intermediate_action_abstractions`。
- **补入** `continuous_action_decoding` 与 `robot_state_and_proprioception`，修正“只有 tokenized action / RGB+language”的偏差。

因此最终保持 39 个节点，没有为了覆盖热点突破 40 个上限。

## 4. 调整了哪些前置关系

- `cross_embodiment_training_and_action_alignment` **不再依赖** `dataset_mixture_and_sampling`。跨本体的硬前置是 action space + trajectory schema；dataset mixture 是常见实现但不是逻辑必要条件。这样 minimum path 也保持闭合。
- `flow_matching_action_generation` **不要求**先学 diffusion。二者在学习顺序上相邻便于比较，但数学与建模上不是硬依赖；其硬前置只保留 action space + action chunking。
- `downstream_finetuning_and_peft` **不依赖** `pretraining_cotuning_and_auxiliary_objectives`。现实项目可直接 fine-tune released VLA，不必先理解模型原始预训练配方。
- `reasoning_for_action_and_spatial_grounding` **不作为** hierarchical architecture 的硬前置；层级策略可通过预定义技能/子目标工作，不必显式 CoT。
- `human_video_and_latent_action_learning` **不依赖** `world_model_vla_interface`。latent action 可通过 inverse dynamics/representation learning 获得，不应人为制造 World Model 依赖。
- `compressed_action_tokenization` 被移动到 action chunking 之后，因为其核心问题正是压缩高频 action sequence/chunk。

程序校验确认最终 prerequisites 图无环，且 minimum / standard / research 三条路径都满足自身所有硬前置。

## 5. 哪些热点被降级为 P2 或 frontier

- `world_model_vla_interface` → **P2/frontier**：重要，但尚不是现代 VLA 的共同组件。
- `human_video_and_latent_action_learning` → **P2/frontier**：数据规模潜力大，但 latent action 定义、跨本体对齐和真实机器人收益尚未收敛。
- `extended_modalities_3d_tactile_audio` → **P2/frontier**：3D/触觉/力觉对部分任务关键，但不应让多传感器热点支配 VLA 主体。
- reasoning 保留为 **P1/evolving**，没有升 P0；显式 CoT/visual reasoning 的闭环收益仍依任务和实现。
- dual-system/action expert 保留为 **P1/evolving**，没有因 π₀/GR00T 等代表工作而把 fast–slow 结构视为唯一基础架构。

## 6. 接受了哪些审查意见

- **接受：降低 P0 数量。** 初稿中 monolithic architecture、dataset mixture、real-time inference、reasoning 等一度接近 P0；最终 P0 压到 15/39（38.5%），保持“最低必需”含义。
- **接受：模型名不能成为节点。** OpenVLA、π₀、Octo、GR00T、Gemini Robotics 全部只作为 representative works/evidence anchors。
- **接受：数据、评测、部署必须和架构同等可见。** 最终分别有独立模块，避免成为“只会看 backbone/action head”的论文目录。
- **接受：action token 必须消歧。** 这是来源之间最实质的术语冲突之一。
- **接受：World Model 和 RL 必须收窄。** 只保留 VLA 直接接口。
- **接受：稳定性必须影响学习路线。** 三个 frontier 节点全部退出 standard path，只进入 research path。

## 7. 拒绝了哪些审查意见以及原因

- **拒绝加入完整 MDP、控制、SLAM、运动学。** ETH/Cornell 课程把它们作为 Robot Learning 前置，但本用户已有机器人基础，而且这些内容不需要独立 3–5 分钟 VLA 卡；只保留 action/control interface。
- **拒绝把 2026 新模型逐个做节点。** curated repo 显示模型迭代密集，模型名 ID 会快速过时，破坏未来 v2 学习进度稳定性。
- **拒绝把 World Model 升为 P0/P1 主干。** Survey 把它列为重要 advanced/future interface，但尚不能证明所有 VLA 论文必须先掌握它。
- **拒绝单独建“VLN”节点。** 层级 planner-policy、language grounding、generalization 已吸收与 VLA 直接相关的知识；加入完整 VLN 会越界。
- **拒绝 UAV 专属 VLA 节点。** 当前任务明确只编译 VLA 专项通用框架；UAV embodiment 的特殊传感/控制应在未来 UAV curriculum 或应用 overlay 中处理。
- **拒绝背 benchmark 排行榜。** benchmark 变化快；冻结的是 evaluation protocol 和 generalization split 的方法论。

## 8. 仍然需要人工判断的问题

1. **VLA 与 generalist robot policy 的边界。** Octo 一类不以大型 VLM 为主体的 generalist policy 是否在团队内部也统一叫 VLA，需要人工定义项目词汇表。
2. **课程是否保持 manipulation-centric。** 当前证据最成熟的 VLA 仍以 manipulation 为主；如果后续重点转向 mobile manipulation、navigation、humanoid locomotion 或 UAV，需要 overlay，而非悄悄扩大 v1。
3. **安全是否未来独立成节点。** 如果出现成熟、通用、可复现的 VLA safety benchmark/机制，可把 `failure_modes_and_reliability` 拆分。
4. **RL post-training 是否升级 P0。** 若未来 released VLA 的标准 recipe 普遍包含 RL/RFT，P1 将需要上调。
5. **long-horizon memory 是否重新拆分。** 只有当多团队在真实机器人上稳定验证 memory 机制，并形成相对稳定 taxonomy 后再独立。
6. **repo 的版本表示。** 本 v1 用 `year=2026` 表示已验证的维护快照年份；若软件需要可复现实验级 provenance，建议 v2 增加 `retrieved_commit`/`commit_sha` 字段，而不是猜初始发布日期。

## 9. 最终为什么可以冻结为 v1

- 证据不依赖单一 Survey：4 个互补 Survey + 2 门大学课程 + 2 个独立 curated repo + 10 个机制锚点。
- 39 个节点处于用户要求的 20–40 范围，且粒度均可压缩为未来 3–5 分钟微学习卡。
- P0 仅 15 个，没有把大多数节点标成“必学”。
- 19 个 foundation 节点构成稳定骨架；17 个 evolving、3 个 frontier 被显式标记，热点不会支配主体。
- 模型名只作为 representative work，不作为长期 ID；snake_case concept ID 可在 v2 复用。
- 数据、架构、训练、泛化、benchmark、失败诊断、推理和部署均有覆盖。
- JSON 所有 source/module/concept 引用已解析；prerequisites 无环；三个路径满足前置顺序。
- 未生成任何知识卡正文。

因此 v1 可以作为 **reviewed_draft** 冻结供软件读取；“冻结”不代表结论永久不变，而是只有触发条件满足时才开启 v2 变更。

## 10. 下一次建议审查的触发条件

不要只按日期更新。出现以下任一强触发，或两个以上弱触发时，应启动 v2 review：

**强触发：**
- 主流开源/官方 VLA 训练 recipe 出现新的动作表示/生成范式，并在多个机器人/benchmark 上跨团队复现，足以改变 `action_*` P0/P1 结构。
- RL/RFT/interactive post-training 成为多个主流 VLA 的标准阶段，而不是少数专项论文。
- 新的真实机器人 benchmark 或统一 evaluation protocol 被多个团队采用，显著改善当前不可比问题。
- World Model、human-video latent action 或 3D/tactile 中任一方向从“代表性结果”转为多团队、真实机器人、跨任务复现。

**弱触发：**
- dual-system / monolithic / hierarchical taxonomy 出现更稳定的新共识。
- FAST 类 token compression 被新的 universal action representation 取代或扩展。
- 新模型普遍采用不同的 control-frequency / async execution 方案。
- VLA 社区对“VLA”与“generalist robot policy”的命名边界出现实质收敛。
- 当前任一核心来源撤回、链接失效、被更高质量系统综述替代，或关键结论被后续工作系统性反证。

**时间后备线：**即使没有强触发，也建议在约 3 个月后做一次轻量来源刷新；若无结构性变化，应保持 concept ID 和 P0 foundation 不动，只更新 representative works/source_ids。

## 附录：自动校验结果

- `sources.json`：JSON parser 重新读取成功；18 个 source ID 唯一。
- `curriculum_v1.json`：JSON parser 重新读取成功；7 个 module ID、39 个 concept ID 均唯一且符合稳定 snake_case 约定。
- `modules[*].concept_ids`：与 concepts 一一匹配，无漏项、无重复。
- `concept.source_ids`：全部能解析到 `sources.json`；每个节点有 3–5 个来源支持；18 个来源均至少被一个节点使用。
- `prerequisites` / `related_concepts`：全部指向真实 concept ID。
- prerequisites 图：Kahn topological sort 覆盖 39/39 节点，**无依赖环**。
- 学习顺序：research path 中所有 prerequisite 均先于被依赖节点。
- 路径闭包：minimum=15、standard=36、research=39；三条路径内部均无缺失硬前置。
- P0 比例：15/39 = 38.5%，低于半数；P1=21，P2=3。
- Stability：foundation=19，evolving=17，frontier=3；frontier 未进入 standard path。
