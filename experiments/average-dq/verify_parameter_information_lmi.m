% Post-pilot diagnostic using the documented MathWorks LMI feasibility method.
% Bounded search failure is not proof of infeasibility.
projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
resultDir = fullfile(projectRoot, 'results', 'parameter-information-pilot');
data = jsondecode(fileread(fullfile(resultDir, 'matlab-input.json')));
records = struct([]);
for k = 1:numel(data.conditions)
    sample = data.conditions(k);
    if sample.case_x ~= .4 || ~all(sample.bounds >= 1) || ...
            ~(strcmp(sample.name, 'whole-box') || ...
            strcmp(sample.name, 'axis-0-value-3.0') || strcmp(sample.name, 'axis-1-value-3.0'))
        continue
    end
    n = size(sample.center,1);
    setlmis([]);
    pVar = lmivar(1,[n,1]);
    lmiterm([1,1,1,0],1);
    lmiterm([-1,1,1,pVar],1,1);
    for j = 1:size(sample.vertices,1)
        a = squeeze(sample.vertices(j,:,:));
        lmiterm([j+1,1,1,pVar],a',1,'s');
        lmiterm([j+1,1,1,0],1);
    end
    system = getlmis;
    tic;
    [tmin, decisions] = feasp(system,[0,20,1e8,1,1],-1e-4);
    elapsed = toc;
    p = dec2mat(system,decisions,pVar);
    p = (p+p')/2;
    pMin = min(eig(p));
    margin = Inf;
    for j = 1:size(sample.vertices,1)
        a = squeeze(sample.vertices(j,:,:));
        margin = min(margin,-max(eig(a'*p+p*a)));
    end
    % Always re-evaluate the returned matrix rather than trusting tmin alone.
    stable = all(isfinite(p),'all') && pMin > 1e-8 && margin > 1e-6;
    record = struct('name',sample.name,'bounds',sample.bounds,'tmin',tmin, ...
        'seconds',elapsed,'p_min_eigenvalue',pMin,'minimum_q_margin',margin, ...
        'stable_sufficient_condition',stable,'p',p);
    if isempty(records)
        records = record;
    else
        records(end+1) = record; %#ok<SAGROW>
    end
    fprintf('%s: bounded LMI search checked, stable=%d, %.3f s\n', ...
        sample.name,stable,elapsed);
end
assert(numel(records) == 3,'GFM:UnexpectedLmiTasks','Expected exactly three diagnostic tasks.');
summary = struct('matlab_version',version,'max_iterations',20,'records',records, ...
    'scope','Post-hoc bounded common-P LMI diagnostic; failure does not establish infeasibility');
fid = fopen(fullfile(resultDir,'lmi-diagnostic.json'),'w','n','UTF-8');
assert(fid ~= -1,'GFM:OutputOpenFailed','Cannot open result file.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(summary,PrettyPrint=true));
disp('V1_LMI_DIAGNOSTIC_FINISHED');
