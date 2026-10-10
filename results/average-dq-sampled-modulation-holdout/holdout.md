# 保持坐标与一拍命令延迟：冻结参数留出预实验

- 状态：verified-bounded-holdout；192/192 条成对模型比较，0 条待定。
- 与相同坐标的相位匹配一阶滞后标签分歧：72 条。
- 坐标比较 0/96 对标签不同；延迟比较 38/96 对不同。
- 计数不是概率，各条件是同一组模型场景的重复比较。全谱及额外延迟快模态均保存在 holdout.json。
- 只保持局部或全局同步dq调制包络；PI/外环连续。不是全数字、abc/PWM或实机安全周期。

|保持坐标|命令延迟拍数|成对比较|与一阶近似标签分歧|
|---|---:|---:|---:|
|local-control-dq|0|48|9|
|local-control-dq|1|48|27|
|global-synchronous-dq|0|48|8|
|global-synchronous-dq|1|48|28|

## 全部192条比较

|X|PI倍率|Ts(s)|保持|延迟拍数|采样logρ/Ts|近似alpha|采样/近似标签|
|---:|---:|---:|---|---:|---:|---:|---|
|0.2|0.5|0.0001|local-control-dq|0|16.7332864|16.7294146|unstable/unstable|
|0.2|0.5|0.0005|local-control-dq|0|13.146336|13.0868579|unstable/unstable|
|0.2|0.5|0.001|local-control-dq|0|9.27359551|9.49759515|unstable/unstable|
|0.2|0.5|0.002|local-control-dq|0|3.04735796|5.36093052|unstable/unstable|
|0.2|0.5|0.0001|local-control-dq|1|14.8323194|14.8301667|unstable/unstable|
|0.2|0.5|0.0005|local-control-dq|1|477.539763|6.98941217|unstable/unstable|
|0.2|0.5|0.001|local-control-dq|1|156.387414|3.72584967|unstable/unstable|
|0.2|0.5|0.002|local-control-dq|1|184.638995|2.83241883|unstable/unstable|
|0.2|0.5|0.0001|global-synchronous-dq|0|16.7130255|16.7090771|unstable/unstable|
|0.2|0.5|0.0005|global-synchronous-dq|0|13.0382792|12.9769709|unstable/unstable|
|0.2|0.5|0.001|global-synchronous-dq|0|9.03411527|9.26218331|unstable/unstable|
|0.2|0.5|0.002|global-synchronous-dq|0|2.37469927|4.88998672|unstable/unstable|
|0.2|0.5|0.0001|global-synchronous-dq|1|14.7688546|14.7666365|unstable/unstable|
|0.2|0.5|0.0005|global-synchronous-dq|1|477.539761|6.62810166|unstable/unstable|
|0.2|0.5|0.001|global-synchronous-dq|1|156.387415|3.10152624|unstable/unstable|
|0.2|0.5|0.002|global-synchronous-dq|1|184.638992|3.38743649|unstable/unstable|
|0.2|1|0.0001|local-control-dq|0|16.1944381|16.1823499|unstable/unstable|
|0.2|1|0.0005|local-control-dq|0|11.1872977|10.9436561|unstable/unstable|
|0.2|1|0.001|local-control-dq|0|6.17149681|5.71216417|unstable/unstable|
|0.2|1|0.002|local-control-dq|0|-2.24199667|-0.198808029|stable/stable|
|0.2|1|0.0001|local-control-dq|1|13.4684713|13.4551081|unstable/unstable|
|0.2|1|0.0005|local-control-dq|1|498.658027|2.04621088|unstable/unstable|
|0.2|1|0.001|local-control-dq|1|123.634852|-1.86430495|unstable/stable|
|0.2|1|0.002|local-control-dq|1|174.887641|-1.00935148|unstable/stable|
|0.2|1|0.0001|global-synchronous-dq|0|16.1827525|16.1705312|unstable/unstable|
|0.2|1|0.0005|global-synchronous-dq|0|11.1254213|10.8772624|unstable/unstable|
|0.2|1|0.001|global-synchronous-dq|0|6.05163412|5.55719359|unstable/unstable|
|0.2|1|0.002|global-synchronous-dq|0|-2.40624759|-0.593569913|stable/stable|
|0.2|1|0.0001|global-synchronous-dq|1|13.4310293|13.4175844|unstable/unstable|
|0.2|1|0.0005|global-synchronous-dq|1|498.658025|1.77874246|unstable/unstable|
|0.2|1|0.001|global-synchronous-dq|1|123.634854|-2.4950063|unstable/stable|
|0.2|1|0.002|global-synchronous-dq|1|174.887638|-2.13326682|unstable/stable|
|0.2|1.5|0.0001|local-control-dq|0|14.0318982|14.009325|unstable/unstable|
|0.2|1.5|0.0005|local-control-dq|0|8.301004|7.79561862|unstable/unstable|
|0.2|1.5|0.001|local-control-dq|0|3.18583616|1.32500701|unstable/unstable|
|0.2|1.5|0.002|local-control-dq|0|-2.20185089|-2.19511197|stable/stable|
|0.2|1.5|0.0001|local-control-dq|1|10.8255742|10.7972261|unstable/unstable|
|0.2|1.5|0.0005|local-control-dq|1|521.783629|-2.18071775|unstable/stable|
|0.2|1.5|0.001|local-control-dq|1|89.3013981|-2.22697453|unstable/stable|
|0.2|1.5|0.002|local-control-dq|1|166.504782|-2.35578932|unstable/stable|
|0.2|1.5|0.0001|global-synchronous-dq|0|14.0250818|14.0023837|unstable/unstable|
|0.2|1.5|0.0005|global-synchronous-dq|0|8.26675037|7.75707319|unstable/unstable|
|0.2|1.5|0.001|global-synchronous-dq|0|3.1316144|1.2340984|unstable/unstable|
|0.2|1.5|0.002|global-synchronous-dq|0|-2.30061577|-2.2943123|stable/stable|
|0.2|1.5|0.0001|global-synchronous-dq|1|10.8037525|10.7753504|unstable/unstable|
|0.2|1.5|0.0005|global-synchronous-dq|1|521.783627|-2.2526061|unstable/stable|
|0.2|1.5|0.001|global-synchronous-dq|1|89.3014004|-2.38753988|unstable/stable|
|0.2|1.5|0.002|global-synchronous-dq|1|166.504779|-2.7995561|unstable/stable|
|0.2|2|0.0001|local-control-dq|0|11.4229593|11.3891761|unstable/unstable|
|0.2|2|0.0005|local-control-dq|0|5.38674391|4.58079814|unstable/unstable|
|0.2|2|0.001|local-control-dq|0|0.889960142|-2.15699228|unstable/stable|
|0.2|2|0.002|local-control-dq|0|-2.18076979|-2.17690728|stable/stable|
|0.2|2|0.0001|local-control-dq|1|7.94077192|7.8965486|unstable/unstable|
|0.2|2|0.0005|local-control-dq|1|546.483137|-2.16670905|unstable/stable|
|0.2|2|0.001|local-control-dq|1|54.4009712|-2.19887844|unstable/stable|
|0.2|2|0.002|local-control-dq|1|159.438052|-2.28035174|unstable/stable|
|0.2|2|0.0001|global-synchronous-dq|0|11.4187828|11.3848953|unstable/unstable|
|0.2|2|0.0005|global-synchronous-dq|0|5.36713525|4.55776045|unstable/unstable|
|0.2|2|0.001|global-synchronous-dq|0|0.865329224|-2.19097726|unstable/stable|
|0.2|2|0.002|global-synchronous-dq|0|-2.25145769|-2.24819523|stable/stable|
|0.2|2|0.0001|global-synchronous-dq|1|7.92752109|7.88327225|unstable/unstable|
|0.2|2|0.0005|global-synchronous-dq|1|546.483135|-2.21888754|unstable/stable|
|0.2|2|0.001|global-synchronous-dq|1|54.4009741|-2.3115668|unstable/stable|
|0.2|2|0.002|global-synchronous-dq|1|159.438049|-2.55502411|unstable/stable|
|0.2|3|0.0001|local-control-dq|0|6.25085404|6.19557181|unstable/unstable|
|0.2|3|0.0005|local-control-dq|0|0.328569867|-1.0919136|unstable/stable|
|0.2|3|0.001|local-control-dq|0|-1.78834448|-2.14473399|stable/stable|
|0.2|3|0.002|local-control-dq|0|51.6227762|-2.15727916|unstable/stable|
|0.2|3|0.0001|local-control-dq|1|2.57769669|2.50429799|unstable/unstable|
|0.2|3|0.0005|local-control-dq|1|599.364437|-2.15090676|unstable/stable|
|0.2|3|0.001|local-control-dq|1|-2.16454157|-2.17065717|stable/stable|
|0.2|3|0.002|local-control-dq|1|148.811902|-2.21657367|unstable/stable|
|0.2|3|0.0001|global-synchronous-dq|0|6.24906244|6.19371238|unstable/unstable|
|0.2|3|0.0005|global-synchronous-dq|0|0.321322494|-1.10109499|unstable/stable|
|0.2|3|0.001|global-synchronous-dq|0|-1.79356898|-2.1667842|stable/stable|
|0.2|3|0.002|global-synchronous-dq|0|51.622774|-2.20272418|unstable/stable|
|0.2|3|0.0001|global-synchronous-dq|1|2.57215322|2.49876452|unstable/unstable|
|0.2|3|0.0005|global-synchronous-dq|1|599.364436|-2.18447515|unstable/stable|
|0.2|3|0.001|global-synchronous-dq|1|-2.22232492|-2.241034|stable/stable|
|0.2|3|0.002|global-synchronous-dq|1|148.811898|-2.37360534|unstable/stable|
|0.2|4|0.0001|local-control-dq|0|1.76068961|1.68721386|unstable/unstable|
|0.2|4|0.0005|local-control-dq|0|171.72901|-2.13350827|unstable/stable|
|0.2|4|0.001|local-control-dq|0|12.8287905|-2.13790891|unstable/stable|
|0.2|4|0.002|local-control-dq|0|110.695958|-2.14702808|unstable/stable|
|0.2|4|0.0001|local-control-dq|1|-1.84368011|-1.94000092|stable/stable|
|0.2|4|0.0005|local-control-dq|1|655.41214|-2.14241443|unstable/stable|
|0.2|4|0.001|local-control-dq|1|-2.15049451|-2.15659338|stable/stable|
|0.2|4|0.002|local-control-dq|1|142.075381|-2.18826683|unstable/stable|
|0.2|4|0.0001|global-synchronous-dq|0|1.75981246|1.68629235|unstable/unstable|
|0.2|4|0.0005|global-synchronous-dq|0|171.72901|-2.14157091|unstable/stable|
|0.2|4|0.001|global-synchronous-dq|0|12.8286537|-2.1542056|unstable/stable|
|0.2|4|0.002|global-synchronous-dq|0|110.695957|-2.18034084|unstable/stable|
|0.2|4|0.0001|global-synchronous-dq|1|-1.84632399|-1.94261928|stable/stable|
|0.2|4|0.0005|global-synchronous-dq|1|655.412138|-2.16712487|unstable/stable|
|0.2|4|0.001|global-synchronous-dq|1|-2.18950346|-2.20771526|stable/stable|
|0.2|4|0.002|global-synchronous-dq|1|142.075375|-2.29849666|unstable/stable|
|0.4|0.5|0.0001|local-control-dq|0|17.0514274|17.0447335|unstable/unstable|
|0.4|0.5|0.0005|local-control-dq|0|10.4046724|10.3351945|unstable/unstable|
|0.4|0.5|0.001|local-control-dq|0|3.85472267|4.58528162|unstable/unstable|
|0.4|0.5|0.002|local-control-dq|0|-3.2348497|0.364894142|stable/unstable|
|0.4|0.5|0.0001|local-control-dq|1|13.4839075|13.4768095|unstable/unstable|
|0.4|0.5|0.0005|local-control-dq|1|457.303403|1.58681377|unstable/unstable|
|0.4|0.5|0.001|local-control-dq|1|270.753844|0.0100814511|unstable/unstable|
|0.4|0.5|0.002|local-control-dq|1|169.680892|0.993871389|unstable/unstable|
|0.4|0.5|0.0001|global-synchronous-dq|0|17.0376415|17.0308698|unstable/unstable|
|0.4|0.5|0.0005|global-synchronous-dq|0|10.3258197|10.2537669|unstable/unstable|
|0.4|0.5|0.001|global-synchronous-dq|0|3.67036233|4.39082761|unstable/unstable|
|0.4|0.5|0.002|global-synchronous-dq|0|-3.64282395|-0.0471385098|stable/stable|
|0.4|0.5|0.0001|global-synchronous-dq|1|13.4389142|13.4317799|unstable/unstable|
|0.4|0.5|0.0005|global-synchronous-dq|1|457.303401|1.27023219|unstable/unstable|
|0.4|0.5|0.001|global-synchronous-dq|1|270.753842|-0.493694856|unstable/stable|
|0.4|0.5|0.002|global-synchronous-dq|1|169.680891|0.143704584|unstable/unstable|
|0.4|1|0.0001|local-control-dq|0|14.1848354|14.1634874|unstable/unstable|
|0.4|1|0.0005|local-control-dq|0|5.32816108|4.91297469|unstable/unstable|
|0.4|1|0.001|local-control-dq|0|-3.12021203|-3.12430592|stable/stable|
|0.4|1|0.002|local-control-dq|0|-3.15869813|-3.15304306|stable/stable|
|0.4|1|0.0001|local-control-dq|1|9.36939078|9.33739829|unstable/unstable|
|0.4|1|0.0005|local-control-dq|1|485.317258|-3.13851873|unstable/stable|
|0.4|1|0.001|local-control-dq|1|250.330156|-3.18299489|unstable/stable|
|0.4|1|0.002|local-control-dq|1|169.038963|-3.27910968|unstable/stable|
|0.4|1|0.0001|global-synchronous-dq|0|14.1792135|14.1577888|unstable/unstable|
|0.4|1|0.0005|global-synchronous-dq|0|5.29807537|4.8799067|unstable/unstable|
|0.4|1|0.001|global-synchronous-dq|0|-3.19215483|-3.21535921|stable/stable|
|0.4|1|0.002|global-synchronous-dq|0|-3.34588115|-3.34764566|stable/stable|
|0.4|1|0.0001|global-synchronous-dq|1|9.35112286|9.31913127|unstable/unstable|
|0.4|1|0.0005|global-synchronous-dq|1|485.317256|-3.27967426|unstable/stable|
|0.4|1|0.001|global-synchronous-dq|1|250.330153|-3.49529682|unstable/stable|
|0.4|1|0.002|global-synchronous-dq|1|169.038962|-4.02940033|unstable/stable|
|0.4|1.5|0.0001|local-control-dq|0|10.4204809|10.3826034|unstable/unstable|
|0.4|1.5|0.0005|local-control-dq|0|0.830909462|-0.0515883762|unstable/stable|
|0.4|1.5|0.001|local-control-dq|0|-3.10654509|-3.11074072|stable/stable|
|0.4|1.5|0.002|local-control-dq|0|-3.13416394|-3.12935694|stable/stable|
|0.4|1.5|0.0001|local-control-dq|1|5.09915993|5.04117379|unstable/unstable|
|0.4|1.5|0.0005|local-control-dq|1|515.071405|-3.11997913|unstable/stable|
|0.4|1.5|0.001|local-control-dq|1|231.179201|-3.14852447|unstable/stable|
|0.4|1.5|0.002|local-control-dq|1|169.524693|-3.20913988|unstable/stable|
|0.4|1.5|0.0001|global-synchronous-dq|0|10.4178757|10.379944|unstable/unstable|
|0.4|1.5|0.0005|global-synchronous-dq|0|0.818837895|-0.065504615|unstable/stable|
|0.4|1.5|0.001|global-synchronous-dq|0|-3.14864353|-3.16982857|stable/stable|
|0.4|1.5|0.002|global-synchronous-dq|0|-3.25880126|-3.25278738|stable/stable|
|0.4|1.5|0.0001|global-synchronous-dq|1|5.09102483|5.0330683|unstable/unstable|
|0.4|1.5|0.0005|global-synchronous-dq|1|515.071404|-3.21054813|unstable/stable|
|0.4|1.5|0.001|global-synchronous-dq|1|231.179199|-3.34208146|unstable/stable|
|0.4|1.5|0.002|global-synchronous-dq|1|169.524693|-3.65203639|unstable/stable|
|0.4|2|0.0001|local-control-dq|0|6.95344177|6.90031431|unstable/unstable|
|0.4|2|0.0005|local-control-dq|0|-2.53098453|-3.09702122|stable/stable|
|0.4|2|0.001|local-control-dq|0|-3.09956648|-3.10378641|stable/stable|
|0.4|2|0.002|local-control-dq|0|-3.12204307|-3.11755384|stable/stable|
|0.4|2|0.0001|local-control-dq|1|1.53458087|1.45495096|unstable/unstable|
|0.4|2|0.0005|local-control-dq|1|546.16783|-3.11063075|unstable/stable|
|0.4|2|0.001|local-control-dq|1|215.092459|-3.13163415|unstable/stable|
|0.4|2|0.002|local-control-dq|1|171.037546|-3.17569072|unstable/stable|
|0.4|2|0.0001|global-synchronous-dq|0|6.95208799|6.8989232|unstable/unstable|
|0.4|2|0.0005|global-synchronous-dq|0|-2.53632771|-3.11853835|stable/stable|
|0.4|2|0.001|global-synchronous-dq|0|-3.12732284|-3.14751121|stable/stable|
|0.4|2|0.002|global-synchronous-dq|0|-3.21740219|-3.20787711|stable/stable|
|0.4|2|0.0001|global-synchronous-dq|1|1.53054579|1.45095691|unstable/unstable|
|0.4|2|0.0005|global-synchronous-dq|1|546.167829|-3.17728153|unstable/stable|
|0.4|2|0.001|global-synchronous-dq|1|215.092456|-3.27165519|unstable/stable|
|0.4|2|0.002|global-synchronous-dq|1|171.037546|-3.48554636|unstable/stable|
|0.4|3|0.0001|local-control-dq|0|1.47898748|1.40240963|unstable/unstable|
|0.4|3|0.0005|local-control-dq|0|-3.09148738|-3.09223718|stable/stable|
|0.4|3|0.001|local-control-dq|0|-3.09248463|-3.0967101|stable/stable|
|0.4|3|0.002|local-control-dq|0|-3.11001662|-3.1057616|stable/stable|
|0.4|3|0.0001|local-control-dq|1|-3.09043034|-3.0904579|stable/stable|
|0.4|3|0.0005|local-control-dq|1|611.202791|-3.10121827|unstable/stable|
|0.4|3|0.001|local-control-dq|1|205.006283|-3.11495327|unstable/stable|
|0.4|3|0.002|local-control-dq|1|176.71869|-3.14335664|unstable/stable|
|0.4|3|0.0001|global-synchronous-dq|0|1.47852455|1.4019279|unstable/unstable|
|0.4|3|0.0005|global-synchronous-dq|0|-3.1031485|-3.10646675|stable/stable|
|0.4|3|0.001|global-synchronous-dq|0|-3.10627502|-3.12547135|stable/stable|
|0.4|3|0.002|global-synchronous-dq|0|-3.17737548|-3.16452545|stable/stable|
|0.4|3|0.0001|global-synchronous-dq|1|-3.09883869|-3.09895984|stable/stable|
|0.4|3|0.0005|global-synchronous-dq|1|611.20279|-3.14482151|unstable/stable|
|0.4|3|0.001|global-synchronous-dq|1|205.00628|-3.2050278|unstable/stable|
|0.4|3|0.002|global-synchronous-dq|1|176.718691|-3.33588607|unstable/stable|
|0.4|4|0.0001|local-control-dq|0|-2.38816355|-2.4794911|stable/stable|
|0.4|4|0.0005|local-control-dq|0|15.3367419|-3.08978332|unstable/stable|
|0.4|4|0.001|local-control-dq|0|-3.08890353|-3.09312446|stable/stable|
|0.4|4|0.002|local-control-dq|0|-3.10403817|-3.09986628|stable/stable|
|0.4|4|0.0001|local-control-dq|1|-3.08842481|-3.08845243|stable/stable|
|0.4|4|0.0005|local-control-dq|1|678.564328|-3.09648546|unstable/stable|
|0.4|4|0.001|local-control-dq|1|242.313735|-3.10668723|unstable/stable|
|0.4|4|0.002|local-control-dq|1|185.247843|-3.12762065|unstable/stable|
|0.4|4|0.0001|global-synchronous-dq|0|-2.38835359|-2.4796913|stable/stable|
|0.4|4|0.0005|global-synchronous-dq|0|15.3367418|-3.10041231|unstable/stable|
|0.4|4|0.001|global-synchronous-dq|0|-3.09584981|-3.11455106|stable/stable|
|0.4|4|0.002|global-synchronous-dq|0|-3.15786257|-3.14340779|stable/stable|
|0.4|4|0.0001|global-synchronous-dq|1|-3.09468992|-3.09480978|stable/stable|
|0.4|4|0.0005|global-synchronous-dq|1|678.564327|-3.12888173|unstable/stable|
|0.4|4|0.001|global-synchronous-dq|1|242.313732|-3.17306001|unstable/stable|
|0.4|4|0.002|global-synchronous-dq|1|185.247845|-3.26707106|unstable/stable|

## 核验和边界

- 先核原旋转R的导数符号与独立global命令Jacobian，再核理想反馈坐标不变。
- 每基础点使用两种线性化步长；冻结残差门和指标差异不确定带，不强行给近界标签。
- 延迟模型是16状态增广矩阵；小Ts匹配14个慢模态，同时单列2个快模态及其增率，完整稳定分类不删快根。
- 4种坐标/延迟条件均有DOP853逐周期独立传播；两个不同X点有global无延迟及一拍非线性周期map差分。
- 相位匹配滞后tau=(拍数+0.5)Ts仍非等价执行器；不存在物理实现优劣或安全周期结论。

```powershell
python experiments/average-dq/run_sampled_modulation_holdout.py
```

- Frozen holdout X values differ from the pilot, but both belong to one team-built single-converter model.
- All PI, outer-loop, measurement and phase states remain continuous; only a command envelope is held.
- Global-synchronous dq is not fixed physical alpha-beta/abc/PWM voltage; carrier/reference-frame implementation is not modeled.
- One-step delay means old held command is applied this cycle and present command is queued for the next; no other computational pipeline.
- Phase-matched lag is not an equivalent actuator; two coordinate choices and delays define different modeling assumptions.
- 192 records and disagreement counts are paired deterministic model comparisons, not independent trials or probabilities.
- No EMT/hardware/external physical confirmation, no safe sampling-period prescription, no continuous parameter-domain theorem.
- Novelty not established; existing ZOH, sampled feedback and matrix-exponential methods are reused.
