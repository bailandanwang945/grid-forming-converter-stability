% Independently check exported matrices with MATLAB eig and lyap.
% This is solver cross-checking, not an independently derived physical model.
projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
resultDir = fullfile(projectRoot, 'results', 'parameter-information-pilot');
data = jsondecode(fileread(fullfile(resultDir, 'matlab-input.json')));
conditionMismatch = 0;
pointMismatch = 0;
maxResidual = 0;
for k = 1:numel(data.conditions)
    sample = data.conditions(k);
    a = sample.center;
    p = lyap(a', eye(size(a)));
    p = (p+p')/2;
    residual = norm(a'*p+p*a+eye(size(a)), 2);
    scale = max(1, norm(a,2)*norm(p,2));
    eigP = eig(p);
    gap = min(abs(eigP));
    margin = Inf;
    for j = 1:size(sample.vertices, 1)
        vertex = squeeze(sample.vertices(j,:,:));
        margin = min(margin, -max(eig(vertex'*p+p*vertex)));
    end
    label = 'pending';
    if all(isfinite(p), 'all') && residual <= 1e-8*scale && ...
            gap > 1e-10*max(1,norm(p,2)) && margin > 1e-8*scale
        if any(eigP < 0)
            label = 'unstable';
        else
            label = 'stable';
        end
    end
    conditionMismatch = conditionMismatch + ~strcmp(label, sample.expected);
    maxResidual = max(maxResidual, residual);
end
for k = 1:numel(data.points)
    sample = data.points(k);
    alpha = max(real(eig(sample.matrix)));
    label = 'pending';
    if alpha < -1e-5
        label = 'stable';
    elseif alpha > 1e-5
        label = 'unstable';
    end
    pointMismatch = pointMismatch + ~strcmp(label, sample.expected);
end
assert(conditionMismatch == 0 && pointMismatch == 0, 'GFM:PilotMismatch', ...
    'MATLAB and Python classifications disagree.');
summary = struct('matlab_version', version, 'conditions', numel(data.conditions), ...
    'points', numel(data.points), 'condition_mismatch', conditionMismatch, ...
    'point_mismatch', pointMismatch, 'max_lyapunov_residual', maxResidual, ...
    'scope', 'Independent solver checks of shared exported matrices only');
fid = fopen(fullfile(resultDir, 'matlab-crosscheck.json'), 'w', 'n', 'UTF-8');
assert(fid ~= -1, 'GFM:OutputOpenFailed', 'Cannot open result file.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(summary, PrettyPrint=true));
disp(summary);
disp('V1_MATLAB_CROSSCHECK_OK');
