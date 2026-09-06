# VLA Curriculum v1

> 状态：`reviewed_draft`
> 检索日期：2026-09-06
> 节点数：39（P0=15，P1=21，P2=3）
> 稳定性：foundation=19，evolving=17，frontier=3

## 1. 课程定位与边界

本课程面向已经具备深度学习、机器人与科研项目基础的学习者，目标不是从通用数学/编程开始，而是形成一套足以支撑 **VLA 前沿论文阅读、模型设计理解、项目参与、实验审查与技术表达** 的稳定知识图谱。课程以“能力栈 + 设计决策 + 生命周期”为主轴：先限定 VLA 问题与必要前置，再处理多模态输入、动作表示/生成、系统架构、训练与数据、泛化评测和部署。

**明确不扩张的内容：**完整强化学习课程、SLAM、运动学/动力学、传统控制器设计、机械结构、通用 VLM/LLM 训练、通用 World Model、VLN 全栈、通用 agent memory、3D vision/触觉完整课程。它们只在与 VLA 的输入、动作、训练、层级接口、Sim2Real 或部署有直接关系时出现。

**VLA 口径：**采用“广义 VLA + 现代 VLM-based VLA 重点”的兼容定义。这样既能解释 RT-2/OpenVLA/π₀/GR00T/Gemini Robotics，也能把 Octo 一类 generalist robot policy 作为相邻参照，而不强行把所有 generalist policy 都等同于大 VLM-based VLA。

## 2. 来源选择说明

最终证据池包含 **4 篇 Survey、2 门大学课程、2 个 curated repository、10 篇奠基/代表论文**。Survey 不采用单一目录：TNNLS Survey 用于宽领域边界；IEEE Access Review 用于真实机器人 full-stack；Large VLM Survey 用于架构分类与前沿；Action Tokenization Survey 用于动作表示术语消歧。课程仅用于校准前置与顺序，代表论文只作为机制锚点，不把模型名变成课程主体。

没有发现一门已经成熟到可作为“纯 VLA 专项教材”的大学课程，因此没有强行凑一个 VLA-only syllabus。ETH Zurich 2026 的课程明确从 imitation/RL/generative/Transformer/world models 过渡到 VLA/foundation models；Cornell 2026 提供端到端视觉运动策略、迁移、多任务、生成模型和 Transformer policy 的第二条独立课程证据。两者只被抽取 VLA 直接相关部分。

GitHub repository 没有像论文一样的正式“出版年份”。`sources.json` 中两个 repo 的 `year=2026` 表示本次审查所验证到的**维护快照年份**，不是声称其首次创建于 2026。

### 主来源清单

- **survey_ma_2026** — A Survey on Vision-Language-Action Models for Embodied AI — Yueen Ma, Zixing Song, Yuzheng Zhuang, Jianye Hao, Irwin King — 2026 — IEEE Transactions on Neural Networks and Learning Systems / arXiv
  https://arxiv.org/abs/2405.14093
  作用：支持 VLA 定义、视觉表示、策略架构、世界模型接口、推理、评测与领域边界。
- **survey_real_world_2025** — Vision-Language-Action Models for Robotics: A Review Towards Real-World Applications — Kento Kawaharazuka, Jihoon Oh, Jun Yamada, Ingmar Posner, Yuke Zhu — 2025 — IEEE Access / arXiv
  https://arxiv.org/abs/2510.07077
  作用：作为训练—数据—推理—部署—评测主干证据，尤其支持动作生成、微调、跨本体、延迟和失败模式节点。
- **survey_large_vlm_2025** — Large VLM-based Vision-Language-Action Models for Robotic Manipulation: A Survey — Rui Shao, Wei Li, Lingsen Zhang, Renshan Zhang, Zhiyang Liu, Ran Chen, Liqiang Nie — 2025 — arXiv
  https://arxiv.org/abs/2508.13073
  作用：支持系统架构分类、推理与中间表示、VLA 后训练和前沿扩展的稳定性判断。
- **survey_action_tokenization_2025** — A Survey on Vision-Language-Action Models: An Action Tokenization Perspective — Yifan Zhong, Fengshuo Bai, Shaofei Cai, Xuchuan Huang, Zhang Chen, Xiaowei Zhang, Yuanfei Wang, Shaoyang Guo, Tianrui Guan, Ka Nam Lui, Zhiquan Qi, Yitao Liang, Yuanpei Chen, Yaodong Yang — 2025 — arXiv
  https://arxiv.org/abs/2507.01925
  作用：支持动作离散化与压缩、原始动作与中间动作抽象、latent action、人类视频和 reasoning 节点。
- **course_eth_robot_learning_2026** — Robot Learning: From Fundamentals to Foundation Models — Oier Mees — 2026 — ETH Zurich
  https://cvg.ethz.ch/lectures/Robot-Learning/
  作用：用于校准必要前置、学习顺序以及生成式策略、序列建模、世界模型与 foundation policy 的衔接。
- **course_cornell_robot_learning_2026** — CS 4756/5756 Robot Learning — Kuan Fang — 2026 — Cornell University
  https://www.cs.cornell.edu/courses/cs4756/2026sp/
  作用：用于验证行为克隆、视觉表示、Sim2Real、迁移、生成策略和 sequence policy 的先后关系；不把通用 RL/控制整段纳入 VLA 课程。
- **repo_awesome_vla_official_2026** — Awesome VLA — Yueen Ma, Zixing Song, Yuzheng Zhuang, Jianye Hao, Irwin King — 2026 — GitHub / Official survey repository
  https://github.com/yueen-ma/Awesome-VLA
  作用：用于交叉核对领域覆盖、前沿更新信号、评测/平台/效率/RL 等新分支。
- **repo_awesome_vla_robotics_2026** — Awesome VLA for Robotics — Jiaqi Liu — 2026 — GitHub
  https://github.com/Jiaaqiliu/Awesome-VLA-Robotics
  作用：作为第二个独立 curated repo 进行遗漏扫描和术语变化检查，尤其覆盖 dual-system、3D/触觉、效率、RL post-training 与新 benchmark。
- **paper_rt2_2023** — RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control — Anthony Brohan et al. — 2023 — arXiv / Google DeepMind
  https://arxiv.org/abs/2307.15818
  作用：支持 VLA 问题定义、VLM 到动作的迁移、动作 token、联合训练和语义泛化。
- **paper_diffusion_policy_2023** — Diffusion Policy: Visuomotor Policy Learning via Action Diffusion — Cheng Chi, Zhenjia Xu, Siyuan Feng, Eric Cousineau, Yilun Du, Benjamin Burchfiel, Russ Tedrake, Shuran Song — 2023 — arXiv
  https://arxiv.org/abs/2303.04137
  作用：支持 diffusion 动作生成、连续动作分布、action horizon 与部署时滚动执行。
- **paper_act_2023** — Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware — Tony Z. Zhao, Vikash Kumar, Sergey Levine, Chelsea Finn — 2023 — arXiv
  https://arxiv.org/abs/2304.13705
  作用：支持行为克隆、action chunking、序列策略、示范质量与闭环执行。
- **paper_open_x_embodiment_2024** — Open X-Embodiment: Robotic Learning Datasets and RT-X Models — Open X-Embodiment Collaboration — 2024 — ICRA / arXiv
  https://arxiv.org/abs/2310.08864
  作用：支持机器人轨迹 schema、数据混合、跨本体动作对齐、泛化与 generalist policy 预训练。
- **paper_octo_2024** — Octo: An Open-Source Generalist Robot Policy — Octo Model Team, Dibya Ghosh, Homer Walke, Karl Pertsch, Kevin Black, Oier Mees, Sudeep Dasari, Joey Hejna, Tobias Kreiman, Charles Xu, Jianlan Luo, You Liang Tan, Lawrence Yunliang Chen, Pannag Sanketi, Quan Vuong, Ted Xiao, Dorsa Sadigh, Chelsea Finn, Sergey Levine — 2024 — arXiv
  https://arxiv.org/abs/2405.12213
  作用：支持任务条件化、数据混合、跨本体训练、动作头、微调和 VLA 与传统/通用机器人策略的边界。
- **paper_openvla_2024** — OpenVLA: An Open-Source Vision-Language-Action Model — Moo Jin Kim, Karl Pertsch, Siddharth Karamcheti, Ted Xiao, Ashwin Balakrishna, Suraj Nair, Rafael Rafailov, Ethan Foster, Grace Lam, Pannag Sanketi, Quan Vuong, Thomas Kollar, Benjamin Burchfiel, Russ Tedrake, Dorsa Sadigh, Sergey Levine, Percy Liang, Chelsea Finn — 2024 — arXiv
  https://arxiv.org/abs/2406.09246
  作用：支持 VLM/Vision backbone、动作 token、fine-tuning/PEFT、数据训练、泛化与部署效率。
- **paper_pi0_2025** — π₀: A Vision-Language-Action Flow Model for General Robot Control — Kevin Black, Noah Brown, Danny Driess, Adnan Esmail, Michael Robert Equi, Chelsea Finn, Niccolo Fusai, Lachy Groom, Karol Hausman, Brian Ichter, Szymon Jakubczak, Tim Jones, Liyiming Ke, Sergey Levine, Adrian Li-Bell, Mohith Mothukuri, Suraj Nair, Karl Pertsch, Lucy Xiaoyang Shi, Laura Smith, James Tanner, Quan Vuong, Anna Walling, Haohuan Wang, Ury Zhilinsky — 2025 — Robotics: Science and Systems
  https://www.roboticsproceedings.org/rss21/p010.html
  作用：支持 flow matching、连续 action expert、跨平台数据训练、fine-tuning 与通用策略。
- **paper_fast_2025** — FAST: Efficient Action Tokenization for Vision-Language-Action Models — Karl Pertsch, Kyle Stachowicz, Brian Ichter, Danny Driess, Suraj Nair, Quan Vuong, Oier Mees, Chelsea Finn, Sergey Levine — 2025 — Robotics: Science and Systems
  https://www.roboticsproceedings.org/rss21/p012.html
  作用：支持 action discretization、compressed tokenization、控制频率、序列长度与训练/推理效率。
- **paper_groot_n1_2025** — GR00T N1: An Open Foundation Model for Generalist Humanoid Robots — NVIDIA: Johan Bjorck et al. — 2025 — arXiv / NVIDIA
  https://arxiv.org/abs/2503.14734
  作用：支持 dual-system/action-expert 架构、多源数据混合、人类视频、合成数据与多本体训练。
- **paper_gemini_robotics_2025** — Gemini Robotics: Bringing AI into the Physical World — Gemini Robotics Team et al. — 2025 — arXiv / Google DeepMind
  https://arxiv.org/abs/2503.20020
  作用：支持语言/空间 grounding、reasoning、扩展视觉模态、跨本体泛化和安全/可靠性。

## 3. 来源分类冲突与最终取舍

| 冲突 | 来源中的不同口径 | v1 取舍 |
|---|---|---|
| 总体 taxonomy | Ma 等按“组件 → 低层控制 → 高层 planner”；Shao 等按 monolithic / dual-system / hierarchical；Kawaharazuka 等按模态、训练、数据、部署全栈 | 不照抄任何一篇目录，采用“能力栈 + 设计决策 + 生命周期”。架构 taxonomy 降为一个模块内的分析节点。 |
| “VLA”定义 | 有来源把 generalized VLA 定义为 state/instruction→action；RT-2/large-VLM survey 更强调由大型 VLM 迁移而来的 VLA | 课程口径兼容二者，但核心阅读重点是现代 VLM/foundation-model 驱动 VLA；Octo 等用于边界比较。 |
| “action token” | 工程论文常指离散低层动作；Action Tokenization Survey 把 language/code/affordance/trajectory/goal/latent/raw action/reasoning 都称为广义 action token | 分成 `action_discretization_and_tokenization`（可执行低层动作编码）和 `intermediate_action_abstractions`（广义中间动作抽象），避免术语污染。 |
| pretraining / post-training | 有的论文把机器人多数据集训练叫 pretraining，有的强调 VLM pretraining；fine-tuning、co-training、post-training 也交叉使用 | 强制按“VLM 既有预训练 → robot/co-training → downstream fine-tuning → interactive/RL post-training”说明阶段，不把命名当事实。 |
| “System 1 / System 2” | 一些 VLA 用 fast/slow 双系统命名，另一些只称 action expert 或 componentized architecture | 节点命名用 `dual_system_action_expert_architecture`，把 System 1/2 视作常见标签而非统一理论。 |

## 4. 完整模块和节点目录

### 1. 必要前置与 VLA 定义 / Foundations and VLA Framing

**目标：** 建立只与 VLA 直接相关的行为克隆、Transformer sequence policy、VLM grounding 和问题边界。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **VLA 问题定义与领域边界** (`vla_problem_formulation`) | P0 | foundation | 所有 VLA 论文和项目都默认这一问题边界；如果定义不清，后续架构、数据和评测会被混淆。 |
| 2 | **VLA 中的行为克隆** (`behavior_cloning_for_vla`) | P0 | foundation | 当前大多数 VLA 的基础训练仍以机器人示范上的监督/模仿学习为核心，是理解训练损失与失败模式的最低前置。 |
| 3 | **Transformer 策略与序列建模** (`transformer_policy_sequence_modeling`) | P0 | foundation | Transformer 是现代 VLA 最反复出现的策略骨架；只保留序列策略所需部分即可避免回到通用基础课。 |
| 4 | **VLM 骨干与机器人 Grounding** (`vlm_backbone_and_robotic_grounding`) | P0 | foundation | 理解 VLA 与 VLM 的继承关系是阅读现代 VLA 架构、预训练与泛化论述的核心前提。 |

### 2. 多模态输入与表示 / Multimodal Inputs and Representation

**目标：** 理解视觉、语言、机器人状态和扩展传感模态如何被表示、对齐并形成动作条件。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **面向控制的视觉表示** (`visual_representation_for_control`) | P1 | foundation | 视觉表示直接影响 VLA 的对象泛化和空间精度，但已有深度学习基础的学习者无需把它设为最低 P0。 |
| 2 | **语言条件化与指令 Grounding** (`language_conditioning_and_grounding`) | P0 | foundation | 语言是 VLA 与纯视觉运动策略的关键条件变量，论文中的泛化和 reasoning 结论通常依赖此节点。 |
| 3 | **机器人状态与本体感觉输入** (`robot_state_and_proprioception`) | P1 | foundation | 真实 VLA 往往不仅输入 RGB；理解 proprioception 是复现项目和处理跨本体数据的必要工程知识。 |
| 4 | **多模态融合与 Token 接口** (`multimodal_fusion_and_token_interface`) | P1 | foundation | 不同 VLA 名称变化很快，但模态如何对齐并通过接口传到动作模块是相对稳定的设计问题。 |
| 5 | **时间上下文与观测历史** (`temporal_context_and_observation_history`) | P1 | foundation | 时序条件是理解 action chunk、闭环执行和长任务失效的桥梁，但长期记忆仍不足以作为 P0 独立基础。 |
| 6 | **3D、触觉与其他扩展模态** (`extended_modalities_3d_tactile_audio`) | P2 | frontier | 3D/触觉正在快速发展且对接触丰富任务很重要，但尚非所有 VLA 的共同必要条件，适合作为遇到项目时学习的前沿节点。 |

### 3. 动作表示与生成 / Action Representation and Generation

**目标：** 掌握 action space、tokenization、chunking，以及 AR、diffusion、flow matching 等动作生成范式的统一比较框架。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **动作空间与控制参数化** (`action_space_and_control_parameterization`) | P0 | foundation | 所有动作 token、diffusion/flow head 和跨本体训练最终都落到具体可执行 action space；这是不可跳过的共同基础。 |
| 2 | **可执行动作离散化与 Tokenization** (`action_discretization_and_tokenization`) | P0 | foundation | 动作 tokenization 是 VLM-style 自回归 VLA 的核心接口，也是高频控制、效率和跨本体设计反复讨论的问题。 |
| 3 | **连续动作解码** (`continuous_action_decoding`) | P1 | foundation | 连续输出是与 tokenized AR 同等重要的基础分支，帮助统一理解 regression、diffusion 和 flow action heads。 |
| 4 | **Action Chunking 与预测时域** (`action_chunking_and_horizon`) | P0 | foundation | action chunk 已跨 Transformer、diffusion、flow VLA 重复出现，是理解低层策略和实时执行的共同机制。 |
| 5 | **压缩式动作 Tokenization** (`compressed_action_tokenization`) | P1 | evolving | 这一机制已形成清晰技术方向但仍快速演进，值得系统掌握而不应被固定为唯一 action tokenizer。 |
| 6 | **自回归动作生成** (`autoregressive_action_generation`) | P0 | foundation | AR 是现代 VLA 最主要的动作生成范式之一，也是理解其与 LLM/VLM 统一建模关系的核心。 |
| 7 | **Diffusion 动作生成** (`diffusion_action_generation`) | P0 | foundation | Diffusion 已成为 VLA/action expert 的主流生成机制之一，理解它是阅读大量 2024–2026 工作的必要能力。 |
| 8 | **Flow Matching 动作生成** (`flow_matching_action_generation`) | P1 | evolving | Flow matching 已有代表性通用 VLA 采用，但动作生成范式仍快速演进，因此放 P1/evolving 而非固定成基础唯一答案。 |

### 4. VLA 架构与系统接口 / VLA Architectures and System Interfaces

**目标：** 比较 monolithic、dual-system/action expert、hierarchical planner-policy 及中间动作抽象，并限定 reasoning/world-model 的位置。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **单体式 VLA 架构** (`monolithic_vla_architecture`) | P1 | evolving | 这是理解现代 VLA 架构谱系的重要参照，但“单体/双系统”是分析框架而非所有论文都使用的原生术语，因此不升为 P0。 |
| 2 | **双系统与 Action Expert 架构** (`dual_system_action_expert_architecture`) | P1 | evolving | 该形态已成为重要架构路线，直接关联连续动作和实时性，但具体耦合方式仍快速演进。 |
| 3 | **层级 Planner–Policy 架构** (`hierarchical_planner_policy_architecture`) | P1 | evolving | 长时程任务常需要层级接口；理解这一架构有助于读论文和系统项目，但并非所有 VLA 的必要骨架。 |
| 4 | **中间动作抽象** (`intermediate_action_abstractions`) | P1 | evolving | 专项 action-token 综述显示社区对“action token”口径很宽；独立此节点可防止与低层离散 token 混淆，并覆盖层级 VLA 的核心接口。 |
| 5 | **面向动作的推理与空间 Grounding** (`reasoning_for_action_and_spatial_grounding`) | P1 | evolving | 推理正变得重要，但效果与实现仍高度依任务；保持 P1/evolving 防止把短期 CoT 热点误当基础。 |
| 6 | **World Model 与 VLA 的接口** (`world_model_vla_interface`) | P2 | frontier | 与 VLA 的耦合是活跃前沿，但尚未成为所有主流 VLA 的共同组成，因此严格限定为接口型 P2/frontier。 |

### 5. 训练、数据与迁移 / Training, Data and Transfer

**目标：** 理解机器人轨迹数据、混合与跨本体训练、预训练/微调/post-training、人类视频与 Sim2Real。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **机器人数据与轨迹 Schema** (`robot_data_and_trajectory_schema`) | P0 | foundation | VLA 的核心瓶颈是异构机器人轨迹；没有 schema 认知就无法正确读训练代码、数据混合或跨本体论文。 |
| 2 | **数据采集与示范质量** (`data_collection_and_demonstration_quality`) | P1 | foundation | 真实项目的表现高度依赖示范采集与质量；属于经常遇到的工程核心，但不是论文阅读最低前置。 |
| 3 | **多数据集混合与采样** (`dataset_mixture_and_sampling`) | P1 | evolving | 跨源混合是 generalist VLA 的关键工程变量，但最佳策略仍在变化，因此为 P1/evolving。 |
| 4 | **跨本体训练与动作对齐** (`cross_embodiment_training_and_action_alignment`) | P0 | evolving | 现代 VLA 的“generalist”核心含义之一就是跨机器人数据利用；它反复影响数据、架构、微调和泛化。 |
| 5 | **预训练、Co-training 与辅助目标** (`pretraining_cotuning_and_auxiliary_objectives`) | P1 | evolving | 不同论文对“pretrain/post-train”命名不统一；建立阶段化词汇能显著提高论文阅读和技术表达准确性。 |
| 6 | **下游微调与参数高效适配** (`downstream_finetuning_and_peft`) | P0 | evolving | 参与 VLA 项目最常见的入口不是从零预训练而是下游适配；因此保持 P0，即便具体 PEFT 技术会变化。 |
| 7 | **VLA 的 RL / 交互式 Post-training** (`vla_post_training_with_rl`) | P1 | evolving | RL 后训练正在快速进入 VLA，但尚未像 BC/fine-tuning 一样成为所有系统的共同必需步骤，因此放 P1/evolving。 |
| 8 | **人类视频与 Latent Action 学习** (`human_video_and_latent_action_learning`) | P2 | frontier | 数据规模潜力很大但 latent 定义、对齐方法与可靠性仍不统一，适合作为 research-path 的 P2/frontier。 |
| 9 | **仿真增强与 Sim2Real** (`simulation_augmentation_and_sim2real`) | P1 | evolving | VLA 数据扩展和可重复评测越来越依赖仿真，但是否能迁移到真实机器人仍是持续变化的工程问题。 |

### 6. 泛化、评测与可靠性 / Generalization, Evaluation and Reliability

**目标：** 建立可比较的泛化 taxonomy、benchmark/真实机器人评测方法与失败诊断框架。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **VLA 泛化维度与迁移分类** (`generalization_taxonomy`) | P0 | foundation | VLA 的核心卖点是泛化；没有明确 taxonomy 就无法严谨比较模型或进行技术表达，因此为 P0。 |
| 2 | **Benchmark 与评测协议** (`benchmarks_and_evaluation_protocols`) | P0 | foundation | 论文阅读和技术表达不仅要看模型，还要审查评测证据；这是避免被不可比 success rate 误导的 P0 能力。 |
| 3 | **失败模式、可靠性与恢复** (`failure_modes_and_reliability`) | P1 | evolving | 可靠性决定真实部署，但安全/恢复方案仍未标准化；合并为一个 P1 节点避免把泛安全学科过度扩张进 VLA。 |

### 7. 推理与部署 / Inference and Deployment

**目标：** 理解控制频率、延迟、异步 chunk 执行以及压缩/端侧部署对真实 VLA 系统的约束。

| 顺序 | 节点 | Priority | Stability | 保留理由 |
|---:|---|---|---|---|
| 1 | **实时推理、控制频率与延迟预算** (`real_time_inference_and_control_frequency`) | P1 | evolving | VLA 能否真实运行不仅取决于 success rate；实时性是工程实现高频出现的问题，但并非理解所有论文的最低门槛，故 P1。 |
| 2 | **异步 Action Chunk 执行与重规划** (`asynchronous_chunk_execution_and_replanning`) | P1 | evolving | 异步执行正在解决大模型策略的真实延迟问题，已值得 standard path 学习，但具体算法仍快速演进。 |
| 3 | **效率、压缩与端侧部署** (`efficiency_compression_and_on_device`) | P1 | evolving | 真实项目常受算力与延迟约束；方法变化快但问题长期存在，因此为 P1/evolving。 |

## 5. 每个节点的学习边界

以下不是知识卡正文，只固定未来 3–5 分钟微学习卡的边界。

### 必要前置与 VLA 定义

- **VLA 问题定义与领域边界 (`vla_problem_formulation`)**：理解 VLA 作为以视觉、语言及机器人状态为条件、输出可执行动作或动作中间表示的策略范式；区分 VLA、VLM、generalist robot policy 与传统模块化机器人栈。只保留与策略学习直接相关的观测—条件—动作接口，不展开通用机器人学。
  证据：`survey_ma_2026`, `survey_real_world_2025`, `paper_rt2_2023`
- **VLA 中的行为克隆 (`behavior_cloning_for_vla`)**：学习监督式示范学习目标、轨迹条件概率、teacher-forced 训练与 covariate shift/误差累积；聚焦 VLA 最常见的 imitation learning 基线与训练信号，不展开完整 imitation learning 算法谱系。
  证据：`course_eth_robot_learning_2026`, `course_cornell_robot_learning_2026`, `paper_act_2023`, `survey_real_world_2025`
- **Transformer 策略与序列建模 (`transformer_policy_sequence_modeling`)**：只复习与 VLA 直接相关的 self-attention、causal masking、encoder/decoder、序列位置、token readout 与多步序列预测；不从头教授通用 Transformer 数学或语言建模历史。
  证据：`course_eth_robot_learning_2026`, `course_cornell_robot_learning_2026`, `paper_act_2023`, `paper_octo_2024`
- **VLM 骨干与机器人 Grounding (`vlm_backbone_and_robotic_grounding`)**：理解预训练 VLM/多模态 LLM 如何提供视觉语言语义，并通过机器人数据将语义 grounding 到动作；关注 backbone、投影/适配和 co-fine-tuning 的接口，不展开 VLM 全部预训练细节。
  证据：`survey_real_world_2025`, `survey_large_vlm_2025`, `paper_rt2_2023`, `paper_openvla_2024`, `paper_pi0_2025`

### 多模态输入与表示

- **面向控制的视觉表示 (`visual_representation_for_control`)**：学习控制中常用的预训练视觉特征、ViT/CLIP/SigLIP/DINO 类表征、冻结或微调以及语义不变性与精细空间信息的张力；不展开通用视觉识别课程。
  证据：`survey_ma_2026`, `survey_real_world_2025`, `paper_openvla_2024`
- **语言条件化与指令 Grounding (`language_conditioning_and_grounding`)**：学习自然语言指令如何作为任务条件，与视觉对象、空间关系、技能和动作关联；关注 open-vocabulary 指令、语义迁移与歧义，不展开通用 NLP。
  证据：`paper_rt2_2023`, `paper_openvla_2024`, `paper_gemini_robotics_2025`, `survey_real_world_2025`
- **机器人状态与本体感觉输入 (`robot_state_and_proprioception`)**：理解关节/末端执行器/夹爪/base 等 proprioceptive state 如何与图像、语言一起进入策略，包括归一化、时间同步和 embodiment-specific state；不展开状态估计或传感器融合通论。
  证据：`survey_real_world_2025`, `paper_open_x_embodiment_2024`, `paper_octo_2024`
- **多模态融合与 Token 接口 (`multimodal_fusion_and_token_interface`)**：学习视觉、语言、状态和动作信息如何通过 projection、concatenation、cross-attention、query/token compression 或专用接口融合；强调接口形态和信息瓶颈，不展开所有多模态网络变体。
  证据：`survey_real_world_2025`, `repo_awesome_vla_robotics_2026`, `paper_openvla_2024`, `paper_groot_n1_2025`
- **时间上下文与观测历史 (`temporal_context_and_observation_history`)**：学习单帧 vs 历史窗口、时序 token、状态历史和短期记忆如何影响部分可观测性与动作连续性；不把长期 episodic memory 单独扩张为通用 agent memory 课程。
  证据：`paper_diffusion_policy_2023`, `paper_act_2023`, `survey_real_world_2025`
- **3D、触觉与其他扩展模态 (`extended_modalities_3d_tactile_audio`)**：了解点云/深度/3D 几何、触觉/力觉与音频如何补充 RGB+language，重点学习何时它们改变空间或接触 grounding；不展开完整 3D vision、触觉传感或语音技术。
  证据：`survey_real_world_2025`, `survey_large_vlm_2025`, `paper_gemini_robotics_2025`, `repo_awesome_vla_robotics_2026`

### 动作表示与生成

- **动作空间与控制参数化 (`action_space_and_control_parameterization`)**：学习 VLA 输出所对应的 joint/Cartesian end-effector、delta/absolute pose、gripper、base 等动作参数，以及尺度、坐标系、归一化和低层控制器接口；不展开控制器设计和动力学推导。
  证据：`survey_real_world_2025`, `paper_open_x_embodiment_2024`, `paper_octo_2024`
- **可执行动作离散化与 Tokenization (`action_discretization_and_tokenization`)**：学习连续动作逐维分箱、离散 vocab、token 到连续控制值的映射、量化误差和序列长度；这里的 action token 专指可执行低层动作编码，与广义“中间 action tokens”分开。
  证据：`survey_action_tokenization_2025`, `survey_real_world_2025`, `paper_rt2_2023`, `paper_openvla_2024`, `paper_fast_2025`
- **连续动作解码 (`continuous_action_decoding`)**：学习直接 regression/MLP 或生成式 action head 输出连续动作的基本方式，理解 L1/L2、分布建模与连续控制输出的接口；不把 diffusion/flow 的生成过程重复塞进本节点。
  证据：`survey_real_world_2025`, `paper_pi0_2025`, `repo_awesome_vla_robotics_2026`
- **Action Chunking 与预测时域 (`action_chunking_and_horizon`)**：学习一次预测多步动作、observation/action horizon、temporal aggregation/receding horizon 及其对误差累积、平滑性和延迟的影响；不把具体 chunk 长度当通用结论。
  证据：`paper_act_2023`, `paper_diffusion_policy_2023`, `survey_real_world_2025`, `repo_awesome_vla_robotics_2026`
- **压缩式动作 Tokenization (`compressed_action_tokenization`)**：学习先在时间/频率域压缩 action chunk 再量化/编码的思路，以及 DCT、BPE/通用 tokenizer 类机制为何缓解高频动作序列过长；不把 FAST 的具体超参数当作固定知识。
  证据：`paper_fast_2025`, `survey_action_tokenization_2025`, `survey_real_world_2025`
- **自回归动作生成 (`autoregressive_action_generation`)**：学习按 token/维度/时间因果生成动作的训练与推理方式、teacher forcing、exposure/latency 问题和与语言模型统一 vocab 的优势；不展开通用 LLM decoding 技巧。
  证据：`paper_rt2_2023`, `paper_openvla_2024`, `paper_fast_2025`, `survey_real_world_2025`
- **Diffusion 动作生成 (`diffusion_action_generation`)**：学习条件 diffusion policy 对 action chunk 分布建模、前向加噪/反向去噪、训练目标、多模态动作优势与迭代采样成本；不展开图像 diffusion 的全部理论。
  证据：`paper_diffusion_policy_2023`, `paper_octo_2024`, `paper_groot_n1_2025`, `survey_real_world_2025`
- **Flow Matching 动作生成 (`flow_matching_action_generation`)**：学习 conditional flow matching/continuous flow 作为动作生成器的直观目标、与 diffusion 的关系、采样步数和连续 action chunk 接口；不追求所有 ODE/概率流数学细节。
  证据：`paper_pi0_2025`, `survey_real_world_2025`, `survey_large_vlm_2025`

### VLA 架构与系统接口

- **单体式 VLA 架构 (`monolithic_vla_architecture`)**：学习感知、语言理解与动作生成在单一主干/紧密端到端系统中的耦合方式，包括单系统 token 输出和共享表征；不以任何单个模型作为模板。
  证据：`survey_large_vlm_2025`, `survey_real_world_2025`, `paper_rt2_2023`, `paper_openvla_2024`
- **双系统与 Action Expert 架构 (`dual_system_action_expert_architecture`)**：学习慢速 VLM/语义系统与快速动作 expert（diffusion/flow/DiT 等）的紧耦合接口、条件 latent、联合训练与频率分工；不把认知科学 System 1/2 类比当作严格理论。
  证据：`survey_large_vlm_2025`, `survey_real_world_2025`, `paper_pi0_2025`, `paper_groot_n1_2025`
- **层级 Planner–Policy 架构 (`hierarchical_planner_policy_architecture`)**：学习显式将高层任务/子目标规划与低层执行策略解耦的架构，包括 planner-only、planner+policy、技能选择和层级条件；不展开通用 LLM agent orchestration。
  证据：`survey_ma_2026`, `survey_large_vlm_2025`, `repo_awesome_vla_robotics_2026`
- **中间动作抽象 (`intermediate_action_abstractions`)**：学习 language action、code、affordance、keypoint/trajectory、goal state、skill/latent 等位于语言理解与原始控制之间的表示；明确这与“低层动作离散 tokenization”不是同义词。
  证据：`survey_action_tokenization_2025`, `survey_ma_2026`, `survey_large_vlm_2025`
- **面向动作的推理与空间 Grounding (`reasoning_for_action_and_spatial_grounding`)**：学习显式/隐式 embodied reasoning、空间关系、未来目标或 reasoning token 如何服务动作选择，并评估 reasoning 是否真正改善闭环执行；不把通用 Chain-of-Thought 当作必然正确或必须暴露的机制。
  证据：`survey_large_vlm_2025`, `survey_action_tokenization_2025`, `paper_rt2_2023`, `paper_gemini_robotics_2025`
- **World Model 与 VLA 的接口 (`world_model_vla_interface`)**：只学习 world/dynamics model 与 VLA 的直接接口：预测未来观测/latent、为规划或动作选择提供 imagined outcomes、辅助数据/后训练；不展开 world model 完整课程、视频生成或通用 model-based RL。
  证据：`survey_ma_2026`, `survey_large_vlm_2025`, `course_eth_robot_learning_2026`, `repo_awesome_vla_robotics_2026`

### 训练、数据与迁移

- **机器人数据与轨迹 Schema (`robot_data_and_trajectory_schema`)**：学习 episode/trajectory 中图像、语言、state、action、时间戳、任务元数据的对齐和常见统一格式思想（如 RLDS/OXE 风格）；不展开数据库系统或单一框架 API。
  证据：`paper_open_x_embodiment_2024`, `survey_real_world_2025`, `paper_openvla_2024`
- **数据采集与示范质量 (`data_collection_and_demonstration_quality`)**：学习 teleoperation、kinesthetic/proxy interfaces、成功/失败示范、覆盖度、一致性、控制频率和标签质量如何影响模仿学习；不展开硬件遥操作设计。
  证据：`survey_real_world_2025`, `paper_act_2023`, `paper_open_x_embodiment_2024`
- **多数据集混合与采样 (`dataset_mixture_and_sampling`)**：学习跨数据集 mixture、任务/机器人/数据源采样权重、归一化、数据规模不平衡和 quality filtering；不固定某个配比为通用配方。
  证据：`survey_real_world_2025`, `paper_open_x_embodiment_2024`, `paper_octo_2024`, `paper_groot_n1_2025`
- **跨本体训练与动作对齐 (`cross_embodiment_training_and_action_alignment`)**：学习不同机器人在 observation/state/action space、频率、坐标系、DoF 上的异构性，以及统一 schema、embodiment conditioning、action normalization/heads 等对齐策略；不展开具体机器人运动学。
  证据：`paper_open_x_embodiment_2024`, `paper_octo_2024`, `paper_pi0_2025`, `survey_real_world_2025`
- **预训练、Co-training 与辅助目标 (`pretraining_cotuning_and_auxiliary_objectives`)**：区分 VLM 预训练、机器人策略预训练、web/VQA/robot co-training、视觉/语言/视频/自监督辅助目标，理解哪些目标保留语义知识、哪些建立 action grounding；不展开 foundation model 全部预训练配方。
  证据：`paper_rt2_2023`, `paper_openvla_2024`, `paper_pi0_2025`, `survey_real_world_2025`
- **下游微调与参数高效适配 (`downstream_finetuning_and_peft`)**：学习 full fine-tuning、冻结 backbone/只训 action head、LoRA/PEFT、少量 in-domain 数据适配、学习率与知识遗忘风险；不展开 PEFT 的所有 NLP 变体。
  证据：`paper_openvla_2024`, `paper_octo_2024`, `survey_real_world_2025`, `repo_awesome_vla_official_2026`
- **VLA 的 RL / 交互式 Post-training (`vla_post_training_with_rl`)**：只学习 VLA 后训练真正需要的 RL 角色：在 BC/SFT 后用离线/在线/人机交互奖励进一步优化成功率、精度和恢复；理解策略梯度/actor-critic/reward 只到可读论文程度，不展开完整 RL 课程。
  证据：`survey_real_world_2025`, `survey_large_vlm_2025`, `course_eth_robot_learning_2026`, `course_cornell_robot_learning_2026`, `repo_awesome_vla_official_2026`
- **人类视频与 Latent Action 学习 (`human_video_and_latent_action_learning`)**：学习如何从无机器人动作标签的人类/互联网视频中学习 action-relevant latent、inverse dynamics 或中间技能，再适配到机器人；不把视频理解或 world model 全部纳入。
  证据：`survey_action_tokenization_2025`, `survey_large_vlm_2025`, `paper_groot_n1_2025`, `repo_awesome_vla_robotics_2026`
- **仿真增强与 Sim2Real (`simulation_augmentation_and_sim2real`)**：学习 synthetic/sim robot trajectories、domain randomization/real-to-sim 与真实数据混合如何缓解数据成本，并关注视觉/动力学/接触 gap；不展开 simulator API 或完整 sim2real 研究史。
  证据：`survey_real_world_2025`, `course_cornell_robot_learning_2026`, `paper_groot_n1_2025`

### 泛化、评测与可靠性

- **VLA 泛化维度与迁移分类 (`generalization_taxonomy`)**：学习按新对象、场景、语言指令、任务组合、机器人本体/动作空间和数据域区分 generalization/transfer，并区分 zero-shot、few-shot 与 fine-tuned adaptation；不把所有领域泛化理论展开。
  证据：`survey_real_world_2025`, `paper_rt2_2023`, `paper_open_x_embodiment_2024`, `paper_openvla_2024`, `paper_gemini_robotics_2025`
- **Benchmark 与评测协议 (`benchmarks_and_evaluation_protocols`)**：学习任务成功率之外的 trial 设计、seen/unseen split、真实 vs 仿真、控制预算、人工复核、置信区间与常见 benchmark（如 LIBERO、CALVIN、SIMPLER、RoboCasa 等）的用途边界；不背排行榜。
  证据：`survey_real_world_2025`, `survey_ma_2026`, `repo_awesome_vla_robotics_2026`
- **失败模式、可靠性与恢复 (`failure_modes_and_reliability`)**：学习感知/语言 grounding、动作分布、covariate shift、OOD、延迟、长时程误差、数据偏差和硬件执行等失败来源，以及 failure detection、replan/recovery、安全约束的接口；不展开形式化安全验证。
  证据：`survey_real_world_2025`, `survey_ma_2026`, `paper_gemini_robotics_2025`, `repo_awesome_vla_official_2026`

### 推理与部署

- **实时推理、控制频率与延迟预算 (`real_time_inference_and_control_frequency`)**：学习端到端 latency、token/denoising/flow 推理成本、action chunk 生成周期、控制频率、传感/网络/执行延迟和 stale observation；不展开实时操作系统。
  证据：`survey_real_world_2025`, `paper_pi0_2025`, `paper_fast_2025`, `paper_openvla_2024`
- **异步 Action Chunk 执行与重规划 (`asynchronous_chunk_execution_and_replanning`)**：学习模型推理与机器人动作执行并行、chunk overlap、receding-horizon 重规划和 stale action 修正的基本设计；不把单一 Real-Time Chunking 算法细节冻结为标准。
  证据：`survey_real_world_2025`, `survey_action_tokenization_2025`, `repo_awesome_vla_robotics_2026`
- **效率、压缩与端侧部署 (`efficiency_compression_and_on_device`)**：学习量化、缓存、early exit、layer skipping、distillation/小模型、PEFT 与 on-device serving 对延迟、显存和性能的影响；不深入硬件编译器或芯片优化。
  证据：`paper_openvla_2024`, `survey_real_world_2025`, `repo_awesome_vla_official_2026`, `repo_awesome_vla_robotics_2026`

## 6. 推荐学习顺序

推荐按模块顺序学习，但“顺序”不是要求把所有 P1/P2 都学完后才能继续。真正的硬约束由 `prerequisites` 决定。研究路线中的顺序经过 DAG 校验，所有前置都出现在节点之前。

1. **必要前置**：VLA 问题 → BC → Transformer policy → VLM robotic grounding。
2. **多模态表示**：视觉/语言/state → fusion → temporal context；3D/触觉/音频按需。
3. **动作核心**：action space → 低层 tokenization / continuous decoding → chunking → 压缩 token → AR / diffusion / flow。
4. **架构**：monolithic、dual-system、hierarchical → intermediate abstraction / reasoning → world-model interface（按需）。
5. **训练与数据**：trajectory schema → 采集/混合/跨本体 → pretraining/co-training → fine-tuning → RL post-training；人类视频与 Sim2Real 作为扩展。
6. **泛化与评测**：先精确定义 generalization，再学 benchmark protocol，最后学 failure/reliability。
7. **部署**：latency/control Hz → asynchronous chunking → compression/on-device。

## 7. 前置依赖关系

`A <- [B, C]` 表示学 A 前应先掌握 B、C；空前置省略。

- `behavior_cloning_for_vla` <- `vla_problem_formulation`
- `transformer_policy_sequence_modeling` <- `vla_problem_formulation`
- `vlm_backbone_and_robotic_grounding` <- `transformer_policy_sequence_modeling`
- `visual_representation_for_control` <- `vlm_backbone_and_robotic_grounding`
- `language_conditioning_and_grounding` <- `vlm_backbone_and_robotic_grounding`
- `robot_state_and_proprioception` <- `vla_problem_formulation`
- `multimodal_fusion_and_token_interface` <- `vlm_backbone_and_robotic_grounding`, `visual_representation_for_control`
- `temporal_context_and_observation_history` <- `transformer_policy_sequence_modeling`, `robot_state_and_proprioception`
- `extended_modalities_3d_tactile_audio` <- `visual_representation_for_control`, `robot_state_and_proprioception`, `multimodal_fusion_and_token_interface`
- `action_space_and_control_parameterization` <- `behavior_cloning_for_vla`
- `action_discretization_and_tokenization` <- `transformer_policy_sequence_modeling`, `action_space_and_control_parameterization`
- `continuous_action_decoding` <- `action_space_and_control_parameterization`, `transformer_policy_sequence_modeling`
- `action_chunking_and_horizon` <- `behavior_cloning_for_vla`, `action_space_and_control_parameterization`
- `compressed_action_tokenization` <- `action_discretization_and_tokenization`, `action_chunking_and_horizon`
- `autoregressive_action_generation` <- `transformer_policy_sequence_modeling`, `action_discretization_and_tokenization`
- `diffusion_action_generation` <- `behavior_cloning_for_vla`, `action_space_and_control_parameterization`, `action_chunking_and_horizon`
- `flow_matching_action_generation` <- `action_space_and_control_parameterization`, `action_chunking_and_horizon`
- `monolithic_vla_architecture` <- `vlm_backbone_and_robotic_grounding`, `multimodal_fusion_and_token_interface`, `action_space_and_control_parameterization`
- `dual_system_action_expert_architecture` <- `vlm_backbone_and_robotic_grounding`, `multimodal_fusion_and_token_interface`, `action_space_and_control_parameterization`
- `hierarchical_planner_policy_architecture` <- `vla_problem_formulation`, `language_conditioning_and_grounding`, `action_space_and_control_parameterization`
- `intermediate_action_abstractions` <- `language_conditioning_and_grounding`, `action_space_and_control_parameterization`
- `reasoning_for_action_and_spatial_grounding` <- `vlm_backbone_and_robotic_grounding`, `language_conditioning_and_grounding`, `multimodal_fusion_and_token_interface`
- `world_model_vla_interface` <- `vla_problem_formulation`, `temporal_context_and_observation_history`, `action_space_and_control_parameterization`
- `robot_data_and_trajectory_schema` <- `behavior_cloning_for_vla`, `action_space_and_control_parameterization`
- `data_collection_and_demonstration_quality` <- `robot_data_and_trajectory_schema`
- `dataset_mixture_and_sampling` <- `robot_data_and_trajectory_schema`
- `cross_embodiment_training_and_action_alignment` <- `action_space_and_control_parameterization`, `robot_data_and_trajectory_schema`
- `pretraining_cotuning_and_auxiliary_objectives` <- `vlm_backbone_and_robotic_grounding`, `robot_data_and_trajectory_schema`
- `downstream_finetuning_and_peft` <- `vlm_backbone_and_robotic_grounding`, `robot_data_and_trajectory_schema`
- `vla_post_training_with_rl` <- `behavior_cloning_for_vla`, `downstream_finetuning_and_peft`
- `human_video_and_latent_action_learning` <- `temporal_context_and_observation_history`, `robot_data_and_trajectory_schema`
- `simulation_augmentation_and_sim2real` <- `robot_data_and_trajectory_schema`, `data_collection_and_demonstration_quality`
- `generalization_taxonomy` <- `vla_problem_formulation`, `robot_data_and_trajectory_schema`
- `benchmarks_and_evaluation_protocols` <- `generalization_taxonomy`
- `failure_modes_and_reliability` <- `behavior_cloning_for_vla`, `generalization_taxonomy`, `benchmarks_and_evaluation_protocols`
- `real_time_inference_and_control_frequency` <- `action_space_and_control_parameterization`, `action_chunking_and_horizon`
- `asynchronous_chunk_execution_and_replanning` <- `action_chunking_and_horizon`, `real_time_inference_and_control_frequency`
- `efficiency_compression_and_on_device` <- `vlm_backbone_and_robotic_grounding`, `real_time_inference_and_control_frequency`

依赖图已程序校验为 **DAG（无环）**；三个推荐路径也都满足其内部节点的全部硬前置。

## 8. 最小学习路线

只取 15 个 P0；目标是尽快达到“能读主流 VLA 论文、看懂模型/数据/评测主干并准确表达”的最低闭环。

### Minimum Path

1. VLA 问题定义与领域边界 (`vla_problem_formulation`) — P0/foundation
2. VLA 中的行为克隆 (`behavior_cloning_for_vla`) — P0/foundation
3. Transformer 策略与序列建模 (`transformer_policy_sequence_modeling`) — P0/foundation
4. VLM 骨干与机器人 Grounding (`vlm_backbone_and_robotic_grounding`) — P0/foundation
5. 语言条件化与指令 Grounding (`language_conditioning_and_grounding`) — P0/foundation
6. 动作空间与控制参数化 (`action_space_and_control_parameterization`) — P0/foundation
7. 可执行动作离散化与 Tokenization (`action_discretization_and_tokenization`) — P0/foundation
8. Action Chunking 与预测时域 (`action_chunking_and_horizon`) — P0/foundation
9. 自回归动作生成 (`autoregressive_action_generation`) — P0/foundation
10. Diffusion 动作生成 (`diffusion_action_generation`) — P0/foundation
11. 机器人数据与轨迹 Schema (`robot_data_and_trajectory_schema`) — P0/foundation
12. 跨本体训练与动作对齐 (`cross_embodiment_training_and_action_alignment`) — P0/evolving
13. 下游微调与参数高效适配 (`downstream_finetuning_and_peft`) — P0/evolving
14. VLA 泛化维度与迁移分类 (`generalization_taxonomy`) — P0/foundation
15. Benchmark 与评测协议 (`benchmarks_and_evaluation_protocols`) — P0/foundation

## 9. 标准学习路线

包含全部 P0 + P1（36 节点），适合论文阅读 + 代码/数据项目 + 实验设计 + 部署讨论；不要求先学 3 个 frontier P2。

### Standard Path

1. VLA 问题定义与领域边界 (`vla_problem_formulation`) — P0/foundation
2. VLA 中的行为克隆 (`behavior_cloning_for_vla`) — P0/foundation
3. Transformer 策略与序列建模 (`transformer_policy_sequence_modeling`) — P0/foundation
4. VLM 骨干与机器人 Grounding (`vlm_backbone_and_robotic_grounding`) — P0/foundation
5. 面向控制的视觉表示 (`visual_representation_for_control`) — P1/foundation
6. 语言条件化与指令 Grounding (`language_conditioning_and_grounding`) — P0/foundation
7. 机器人状态与本体感觉输入 (`robot_state_and_proprioception`) — P1/foundation
8. 多模态融合与 Token 接口 (`multimodal_fusion_and_token_interface`) — P1/foundation
9. 时间上下文与观测历史 (`temporal_context_and_observation_history`) — P1/foundation
10. 动作空间与控制参数化 (`action_space_and_control_parameterization`) — P0/foundation
11. 可执行动作离散化与 Tokenization (`action_discretization_and_tokenization`) — P0/foundation
12. 连续动作解码 (`continuous_action_decoding`) — P1/foundation
13. Action Chunking 与预测时域 (`action_chunking_and_horizon`) — P0/foundation
14. 压缩式动作 Tokenization (`compressed_action_tokenization`) — P1/evolving
15. 自回归动作生成 (`autoregressive_action_generation`) — P0/foundation
16. Diffusion 动作生成 (`diffusion_action_generation`) — P0/foundation
17. Flow Matching 动作生成 (`flow_matching_action_generation`) — P1/evolving
18. 单体式 VLA 架构 (`monolithic_vla_architecture`) — P1/evolving
19. 双系统与 Action Expert 架构 (`dual_system_action_expert_architecture`) — P1/evolving
20. 层级 Planner–Policy 架构 (`hierarchical_planner_policy_architecture`) — P1/evolving
21. 中间动作抽象 (`intermediate_action_abstractions`) — P1/evolving
22. 面向动作的推理与空间 Grounding (`reasoning_for_action_and_spatial_grounding`) — P1/evolving
23. 机器人数据与轨迹 Schema (`robot_data_and_trajectory_schema`) — P0/foundation
24. 数据采集与示范质量 (`data_collection_and_demonstration_quality`) — P1/foundation
25. 多数据集混合与采样 (`dataset_mixture_and_sampling`) — P1/evolving
26. 跨本体训练与动作对齐 (`cross_embodiment_training_and_action_alignment`) — P0/evolving
27. 预训练、Co-training 与辅助目标 (`pretraining_cotuning_and_auxiliary_objectives`) — P1/evolving
28. 下游微调与参数高效适配 (`downstream_finetuning_and_peft`) — P0/evolving
29. VLA 的 RL / 交互式 Post-training (`vla_post_training_with_rl`) — P1/evolving
30. 仿真增强与 Sim2Real (`simulation_augmentation_and_sim2real`) — P1/evolving
31. VLA 泛化维度与迁移分类 (`generalization_taxonomy`) — P0/foundation
32. Benchmark 与评测协议 (`benchmarks_and_evaluation_protocols`) — P0/foundation
33. 失败模式、可靠性与恢复 (`failure_modes_and_reliability`) — P1/evolving
34. 实时推理、控制频率与延迟预算 (`real_time_inference_and_control_frequency`) — P1/evolving
35. 异步 Action Chunk 执行与重规划 (`asynchronous_chunk_execution_and_replanning`) — P1/evolving
36. 效率、压缩与端侧部署 (`efficiency_compression_and_on_device`) — P1/evolving

## 10. 研究强化路线

包含 39 个节点；在 standard path 上加入扩展模态、World Model–VLA 接口、人类视频/latent action 三个 P2/frontier 节点。该路径是完整 topo 顺序。

### Research Path

1. VLA 问题定义与领域边界 (`vla_problem_formulation`) — P0/foundation
2. VLA 中的行为克隆 (`behavior_cloning_for_vla`) — P0/foundation
3. Transformer 策略与序列建模 (`transformer_policy_sequence_modeling`) — P0/foundation
4. VLM 骨干与机器人 Grounding (`vlm_backbone_and_robotic_grounding`) — P0/foundation
5. 面向控制的视觉表示 (`visual_representation_for_control`) — P1/foundation
6. 语言条件化与指令 Grounding (`language_conditioning_and_grounding`) — P0/foundation
7. 机器人状态与本体感觉输入 (`robot_state_and_proprioception`) — P1/foundation
8. 多模态融合与 Token 接口 (`multimodal_fusion_and_token_interface`) — P1/foundation
9. 时间上下文与观测历史 (`temporal_context_and_observation_history`) — P1/foundation
10. 3D、触觉与其他扩展模态 (`extended_modalities_3d_tactile_audio`) — P2/frontier
11. 动作空间与控制参数化 (`action_space_and_control_parameterization`) — P0/foundation
12. 可执行动作离散化与 Tokenization (`action_discretization_and_tokenization`) — P0/foundation
13. 连续动作解码 (`continuous_action_decoding`) — P1/foundation
14. Action Chunking 与预测时域 (`action_chunking_and_horizon`) — P0/foundation
15. 压缩式动作 Tokenization (`compressed_action_tokenization`) — P1/evolving
16. 自回归动作生成 (`autoregressive_action_generation`) — P0/foundation
17. Diffusion 动作生成 (`diffusion_action_generation`) — P0/foundation
18. Flow Matching 动作生成 (`flow_matching_action_generation`) — P1/evolving
19. 单体式 VLA 架构 (`monolithic_vla_architecture`) — P1/evolving
20. 双系统与 Action Expert 架构 (`dual_system_action_expert_architecture`) — P1/evolving
21. 层级 Planner–Policy 架构 (`hierarchical_planner_policy_architecture`) — P1/evolving
22. 中间动作抽象 (`intermediate_action_abstractions`) — P1/evolving
23. 面向动作的推理与空间 Grounding (`reasoning_for_action_and_spatial_grounding`) — P1/evolving
24. World Model 与 VLA 的接口 (`world_model_vla_interface`) — P2/frontier
25. 机器人数据与轨迹 Schema (`robot_data_and_trajectory_schema`) — P0/foundation
26. 数据采集与示范质量 (`data_collection_and_demonstration_quality`) — P1/foundation
27. 多数据集混合与采样 (`dataset_mixture_and_sampling`) — P1/evolving
28. 跨本体训练与动作对齐 (`cross_embodiment_training_and_action_alignment`) — P0/evolving
29. 预训练、Co-training 与辅助目标 (`pretraining_cotuning_and_auxiliary_objectives`) — P1/evolving
30. 下游微调与参数高效适配 (`downstream_finetuning_and_peft`) — P0/evolving
31. VLA 的 RL / 交互式 Post-training (`vla_post_training_with_rl`) — P1/evolving
32. 人类视频与 Latent Action 学习 (`human_video_and_latent_action_learning`) — P2/frontier
33. 仿真增强与 Sim2Real (`simulation_augmentation_and_sim2real`) — P1/evolving
34. VLA 泛化维度与迁移分类 (`generalization_taxonomy`) — P0/foundation
35. Benchmark 与评测协议 (`benchmarks_and_evaluation_protocols`) — P0/foundation
36. 失败模式、可靠性与恢复 (`failure_modes_and_reliability`) — P1/evolving
37. 实时推理、控制频率与延迟预算 (`real_time_inference_and_control_frequency`) — P1/evolving
38. 异步 Action Chunk 执行与重规划 (`asynchronous_chunk_execution_and_replanning`) — P1/evolving
39. 效率、压缩与端侧部署 (`efficiency_compression_and_on_device`) — P1/evolving

## 11. 未来 1–3 个月最可能需要更新的部分

优先检查下面的 **evolving/frontier** 节点，而不是频繁改动 foundation ID：

- `compressed_action_tokenization`：新的 tokenizer、离散 diffusion、universal action representation 是否形成可复现共识。
- `flow_matching_action_generation` 与 `dual_system_action_expert_architecture`：flow/diffusion/AR/hybrid 是否出现明显的架构收敛或新主流。
- `vla_post_training_with_rl`：RL/RFT/interactive post-training 是否从“部分系统加成”变成通用训练阶段。
- `world_model_vla_interface`、`human_video_and_latent_action_learning`：是否出现跨团队复现且能稳定提升真实机器人泛化的证据；满足后才考虑从 P2 升级。
- `reasoning_for_action_and_spatial_grounding`：显式 reasoning 是否在闭环 success、延迟和可靠性上有稳定净收益，而非只提高中间语义指标。
- `extended_modalities_3d_tactile_audio`：3D/力觉/触觉是否从特定任务扩展为通用 VLA 输入。
- `real_time_inference_and_control_frequency`、`asynchronous_chunk_execution_and_replanning`、`efficiency_compression_and_on_device`：部署优化迭代很快，需跟踪真实 control Hz 而非仅模型 FPS。
- `benchmarks_and_evaluation_protocols`：若出现新的标准化真实机器人 benchmark、统一 trial protocol 或更可信 sim-to-real proxy，应更新代表 benchmark 和评测建议。

**稳定部分默认冻结：**VLA 问题定义、BC、Transformer sequence policy、VLM grounding、action space、基础 tokenization/chunking、AR/diffusion 的核心机制、trajectory schema、泛化 taxonomy 与评测方法论。除非社区术语发生实质迁移，不因新模型发布重命名这些 ID。

## 12. 是否足以支撑论文、项目与技术表达

**论文阅读：足够。** P0 覆盖 VLA 定义、BC/Transformer/VLM、动作表示/生成、机器人数据、跨本体、微调、泛化与评测；P1 补齐架构、数据混合、RL post-training、部署。

**工程实现：足够形成框架，但不是 API 教程。** Standard path 能让学习者理解数据 schema、action convention、fine-tuning、控制频率、异步执行和 benchmark；具体框架（LeRobot、RLDS loader、特定 robot driver）应在项目中按需学习。

**技术表达：足够。** 特别通过 generalization taxonomy、action-token 术语消歧、architecture taxonomy 和 evaluation protocol，能够避免把“VLM 能推理”“zero-shot”“action token”“System 1/2”等模糊词当作未经限定的技术结论。

**保留不确定性：**“VLA”边界本身仍在变化；dual-system、reasoning、World Model、human-video latent action 和 RL post-training 的地位尚未稳定。因此 v1 冻结的是问题与接口，不冻结具体热点模型为核心节点。
