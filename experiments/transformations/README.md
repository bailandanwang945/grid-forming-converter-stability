# 分析变换研究试验

本目录仅修改分析设置，不修改作者物理模型。原始资料保持只读，输出位于`results/`。

## 自动试验入口

项目根目录、已有NumPy/SciPy的Python环境下执行，输出目录必须尚不存在：

```powershell
python experiments/transformations/automatic_search.py --output results/automatic-transform-search/new-run --budget-seconds 240
python experiments/transformations/repeat_automatic_search.py --output results/automatic-transform-search/new-replications
python -m unittest discover -s experiments/transformations -p "test_*.py" -v
```

首轮已保存结果的独立核验：

```powershell
python experiments/transformations/verify_automatic_search.py
```

输入快照归档与逐项哈希比较：

```powershell
python experiments/transformations/freeze_search_inputs.py results/automatic-transform-search/new-run/run.json
```

程序按固定种子产生正参数候选，先检查变换F和网络G的零点及高频适当性，再计算有限频率网格的增益／相位判据。候选配置不会作为Python代码执行，未调用外部LLM或付费API。实现参考OpenEvolve的候选—评估器分离方式，没有安装或复制OpenEvolve源码：<https://github.com/algorithmicsuperintelligence/openevolve>。

## 已有结果及解释

研究记录：`docs/research/automatic-transform-search-2026-10-03.md`。四轮结果提高了一个固定稳定算例的分析不等式余量；进化和随机各有两轮胜出。不能宣称进化策略更优、新物理稳定域或论文定理完成。

80个开发频点与其余920个频点来自同一模型；网络表示识别还使用全部网络频响。这个划分只是冻结候选的密网格检查，不是独立场景验证。正式API和网页功能未接入本试验。

## 作者模型的新阻尼工况

2026-10-03已按作者模型重新生成D=0.1/0.2/0.35，冻结首轮参数作比较，2026-10-05核验完成。没有新增全覆盖稳定工况，停止将这一轮自动调参作为核心创新候选，保留原始结果。

已有结果只读核查（不需要启动MATLAB）：

```powershell
python experiments/transformations/verify_author_damping_holdout.py
```

核查输入身份和保存结果一致性，不是独立重算全部相位／增益。源快照位于`results/automatic-transform-search/new-operating-points-01/source-snapshot/`。

重新生成模型须使用独立且尚不存在的输出目录，在MATLAB项目根目录执行：

```matlab
addpath('experiments/transformations');
export_author_damping_holdout(fullfile(pwd,'results','automatic-transform-search','new-operating-points-rerun'));
```

Python比较脚本当前使用固定路径，且拒绝覆盖已有comparison.json；不能直接执行它来覆写历史结果。复核已有结果优先用上面的只读核查入口。内存紧张时仅对运行子进程设置OPENBLAS_NUM_THREADS、OMP_NUM_THREADS、MKL_NUM_THREADS为1，不更改系统全局配置。
