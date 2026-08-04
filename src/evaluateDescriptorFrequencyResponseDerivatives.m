function result = evaluateDescriptorFrequencyResponseDerivatives( ...
        model, frequenciesHz, options)
%EVALUATEDESCRIPTORFREQUENCYRESPONSEDERIVATIVES Evaluate G(jw) and derivatives.
%   MODEL is a continuous-time descriptor realization with fields A, B, C,
%   D, E and modelId, or a continuous-time LTI model. Derivatives are
%   computed from linear solves, without explicitly forming a resolvent:
%       dG(jw)/dw = -1i*C*(jwE-A)^(-1)*E*(jwE-A)^(-1)*B.

    if nargin < 3 || isempty(options)
        options = struct();
    end
    options = validateOptions(options);
    [A, B, C, D, E, modelId] = normalizeModel(model);
    frequenciesHz = validateFrequencies(frequenciesHz);
    frequencyCount = numel(frequenciesHz);
    outputCount = size(C, 1);
    inputCount = size(B, 2);
    response = NaN(outputCount, inputCount, frequencyCount);
    derivativePerRadSecond = NaN(size(response));
    derivativePerHz = NaN(size(response));
    pencilScale = NaN(1, frequencyCount);
    pencilMinimumSingularValueNormalized = NaN(1, frequencyCount);
    pencilConditionNumber = NaN(1, frequencyCount);
    reciprocalConditionEstimate = NaN(1, frequencyCount);
    scaledPencilSeparation = NaN(1, frequencyCount);
    primalSolveResidual = NaN(1, frequencyCount);
    derivativeSolveResidual = NaN(1, frequencyCount);
    estimatedRelativeForwardError = NaN(1, frequencyCount);
    numericStatus = strings(1, frequencyCount);

    for index = 1:frequencyCount
        omega = 2*pi*frequenciesHz(index);
        if isempty(A)
            response(:, :, index) = D;
            derivativePerRadSecond(:, :, index) = zeros(size(D));
            derivativePerHz(:, :, index) = zeros(size(D));
            pencilScale(index) = 1;
            pencilConditionNumber(index) = 1;
            reciprocalConditionEstimate(index) = 1;
            primalSolveResidual(index) = 0;
            derivativeSolveResidual(index) = 0;
            estimatedRelativeForwardError(index) = 0;
            numericStatus(index) = "resolved-static";
            continue;
        end
        componentScaleA = max([max(abs(real(A)), [], 'all'), ...
            max(abs(imag(A)), [], 'all')]);
        componentScaleE = max([max(abs(real(E)), [], 'all'), ...
            max(abs(imag(E)), [], 'all')]);
        scale = max([componentScaleA, abs(omega)*componentScaleE, 1]);
        if ~isfinite(scale)
            numericStatus(index) = "nonfinite-computation";
            continue;
        end
        scaledPencil = 1i*(omega/scale)*E-A/scale;
        scaledInput = B/scale;
        singularValues = svd(scaledPencil);
        pencilScale(index) = scale;
        pencilMinimumSingularValueNormalized(index) = singularValues(end);
        pencilConditionNumber(index) = cond(scaledPencil, 2);
        reciprocalConditionEstimate(index) = rcond(scaledPencil);
        separationScale = norm(A/scale, 2)+ ...
            abs(omega/scale)*norm(E, 2);
        if separationScale > 0
            scaledPencilSeparation(index) = ...
                singularValues(end)/separationScale;
        end
        if ~isfinite(pencilConditionNumber(index)) || ...
                pencilConditionNumber(index) > options.ConditionNumberLimit
            numericStatus(index) = ...
                "numerical-pending-ill-conditioned-pencil";
            continue;
        end
        factorization = decomposition(scaledPencil, 'lu');
        resolventTimesInput = factorization\scaledInput;
        response(:, :, index) = D+C*resolventTimesInput;
        derivativeRightHandSide = (E*resolventTimesInput)/scale;
        derivativeState = factorization\derivativeRightHandSide;
        derivative = -1i*C*derivativeState;
        derivativePerRadSecond(:, :, index) = derivative;
        derivativePerHz(:, :, index) = 2*pi*derivative;
        primalSolveResidual(index) = normalizedResidual(scaledPencil, ...
            resolventTimesInput, scaledInput);
        derivativeSolveResidual(index) = normalizedResidual( ...
            scaledPencil, derivativeState, derivativeRightHandSide);
        estimatedRelativeForwardError(index) = max( ...
            primalSolveResidual(index), derivativeSolveResidual(index))/ ...
            max(reciprocalConditionEstimate(index), realmin);
        if any(~isfinite(response(:, :, index)), 'all') || ...
                any(~isfinite(derivative), 'all') || ...
                ~isfinite(estimatedRelativeForwardError(index))
            numericStatus(index) = "nonfinite-computation";
        elseif max(primalSolveResidual(index), ...
                derivativeSolveResidual(index)) > options.ResidualTolerance
            numericStatus(index) = "solve-residual-too-large";
        elseif estimatedRelativeForwardError(index) > ...
                options.ForwardErrorProxyLimit
            numericStatus(index) = ...
                "numerical-pending-forward-error-too-large";
        else
            numericStatus(index) = "resolved-double-precision";
        end
    end

    result = struct( ...
        'frequenciesHz', frequenciesHz, ...
        'response', response, ...
        'derivativePerRadSecond', derivativePerRadSecond, ...
        'derivativePerHz', derivativePerHz, ...
        'pencilScale', pencilScale, ...
        'pencilMinimumSingularValueNormalized', ...
            pencilMinimumSingularValueNormalized, ...
        'pencilConditionNumber', pencilConditionNumber, ...
        'reciprocalConditionEstimate', reciprocalConditionEstimate, ...
        'scaledPencilSeparation', scaledPencilSeparation, ...
        'primalSolveResidual', primalSolveResidual, ...
        'derivativeSolveResidual', derivativeSolveResidual, ...
        'estimatedRelativeForwardError', estimatedRelativeForwardError, ...
        'numericStatus', numericStatus, ...
        'modelId', modelId, ...
        'derivativeIndependentVariable', "frequency", ...
        'derivativeUnit', "per-Hz", ...
        'floatingPointCertified', false, ...
        'usedExplicitInverse', false, ...
        'factorizationMethod', "scaled-lu-decomposition", ...
        'method', "descriptor-resolvent-analytic-derivative-v1", ...
        'interpretationBoundary', ...
            ['Analytic formulas are evaluated in double precision. ', ...
             'Resolved status is numerical evidence, not an interval bound.']);
end

function value = normalizedResidual(matrix, solution, rightHandSide)
    denominator = norm(matrix, 2)*norm(solution, 2)+ ...
        norm(rightHandSide, 2);
    if denominator == 0
        value = norm(matrix*solution-rightHandSide, 2);
    else
        value = norm(matrix*solution-rightHandSide, 2)/denominator;
    end
end

function [A, B, C, D, E, modelId] = normalizeModel(model)
    if isstruct(model) && isscalar(model)
        required = {'A', 'B', 'C', 'D', 'E', 'modelId', 'timeUnit'};
        if ~all(isfield(model, required))
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidModel', ...
                ['A descriptor struct requires A, B, C, D, E, modelId, ', ...
                 'and timeUnit.']);
        end
        A = model.A;
        B = model.B;
        C = model.C;
        D = model.D;
        E = model.E;
        modelId = string(model.modelId);
        if string(model.timeUnit) ~= "seconds"
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:TimeUnit', ...
                'Descriptor struct timeUnit must be seconds.');
        end
    elseif isa(model, 'lti')
        if model.Ts ~= 0
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:DiscreteTime', ...
                'Only continuous-time models are supported.');
        end
        if string(model.TimeUnit) ~= "seconds"
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:TimeUnit', ...
                'Only models expressed in seconds are supported.');
        end
        if hasdelay(model)
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:Delay', ...
                'Models with delays are not supported.');
        end
        [A, B, C, D, E] = dssdata(model);
        modelId = "matlab-lti-model";
    else
        error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidModel', ...
            'model must be a descriptor struct or continuous-time LTI model.');
    end
    stateCount = size(A, 1);
    valid = isnumeric(A) && ismatrix(A) && size(A, 2) == stateCount && ...
        isnumeric(E) && isequal(size(E), size(A)) && ...
        isnumeric(B) && size(B, 1) == stateCount && ...
        isnumeric(C) && size(C, 2) == stateCount && ...
        isnumeric(D) && isequal(size(D), [size(C, 1), size(B, 2)]) && ...
        all(isfinite(A), 'all') && all(isfinite(B), 'all') && ...
        all(isfinite(C), 'all') && all(isfinite(D), 'all') && ...
        all(isfinite(E), 'all') && isscalar(modelId) && strlength(modelId) > 0;
    if ~valid
        error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidModel', ...
            'Descriptor matrices must be finite and dimensionally compatible.');
    end
end

function frequenciesHz = validateFrequencies(frequenciesHz)
    if ~(isnumeric(frequenciesHz) && isreal(frequenciesHz) && ...
            isvector(frequenciesHz) && ~isempty(frequenciesHz) && ...
            all(isfinite(frequenciesHz)) && all(frequenciesHz >= 0))
        error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidFrequencies', ...
            'frequenciesHz must be a nonempty finite nonnegative vector.');
    end
    frequenciesHz = frequenciesHz(:).';
end

function options = validateOptions(options)
    defaults = struct('ConditionNumberLimit', 1e12, ...
        'ResidualTolerance', 1e-10, ...
        'ForwardErrorProxyLimit', 1e-6);
    if ~(isstruct(options) && isscalar(options))
        error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidOptions', ...
            'options must be a scalar struct.');
    end
    unknown = setdiff(fieldnames(options), fieldnames(defaults));
    if ~isempty(unknown)
        error('gfm:evaluateDescriptorFrequencyResponseDerivatives:UnknownOption', ...
            'Unknown option: %s.', unknown{1});
    end
    names = fieldnames(defaults);
    for index = 1:numel(names)
        if ~isfield(options, names{index})
            options.(names{index}) = defaults.(names{index});
        end
    end
    for index = 1:numel(names)
        value = options.(names{index});
        if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
                isfinite(value) && value > 0)
            error('gfm:evaluateDescriptorFrequencyResponseDerivatives:InvalidOption', ...
                'Numeric limits must be finite positive scalars.');
        end
    end
end
