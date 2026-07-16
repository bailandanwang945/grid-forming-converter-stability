function result = classifyNumericalRangeAdaptive(A, options)
%CLASSIFYNUMERICALRANGEADAPTIVE Bound the best separation margin adaptively.
%   RESULT = CLASSIFYNUMERICALRANGEADAPTIVE(A) evaluates the normalized
%   margin
%
%       f(theta) = lambda_min((exp(-1i*theta)*A + ...
%                    exp(1i*theta)*A')/2)/norm(A,2)
%
%   on a periodic interval partition. Each active interval has a
%   Lipschitz upper bound. The interval with the largest upper bound is
%   bisected until a geometric classification is established or a
%   configured stopping limit is reached.
%
%   The returned envelope controls angular discretization in exact
%   arithmetic. It does not include floating-point eigensolver error and
%   therefore is not a strict computer-assisted proof.
%
%   RESULT = CLASSIFYNUMERICALRANGEADAPTIVE(A, OPTIONS) accepts:
%       InitialIntervals - initial periodic partition size, default 32
%       MaxEvaluations   - maximum margin evaluations, default 4096
%       OptimalityTol    - normalized envelope-gap target, default 1e-10
%       MinHalfWidth     - minimum interval half-width, default 1e-12 rad
%       RelTol           - normalized geometric tolerance, default 1e-8
%       AbsTol           - dimensional absolute tolerance, default 0

    if nargin < 2 || isempty(options)
        options = struct();
    end

    validateMatrix(A);
    options = validateOptions(options);
    A = double(A);

    scale = norm(A, 2);
    tolerance = max(options.AbsTol, options.RelTol*scale);

    if scale <= options.AbsTol
        result = makeDegenerateResult(scale, tolerance, options);
        return;
    end

    normalizedA = A/scale;
    normalizedTolerance = tolerance/scale;
    intervalWidth = 2*pi/options.InitialIntervals;
    centers = -pi + ((0:options.InitialIntervals-1)+0.5)*intervalWidth;
    halfWidths = repmat(intervalWidth/2, size(centers));
    values = evaluateMargins(normalizedA, centers);
    evaluationCount = numel(values);
    classification = "indeterminate";
    stopReason = "";

    while stopReason == ""
        lowerBound = max(values);
        intervalUpperBounds = values + 2*sin(halfWidths/2);
        upperBound = max(intervalUpperBounds);

        [classification, stopReason] = classifyEnvelope( ...
            lowerBound, upperBound, normalizedTolerance);
        if stopReason ~= ""
            break;
        end

        if upperBound-lowerBound <= options.OptimalityTol
            stopReason = "optimality-gap";
            break;
        end

        [~, splitIndex] = max(intervalUpperBounds);
        if halfWidths(splitIndex) <= options.MinHalfWidth
            stopReason = "minimum-half-width";
            break;
        end

        if evaluationCount+2 > options.MaxEvaluations
            stopReason = "evaluation-budget";
            break;
        end

        parentCenter = centers(splitIndex);
        childHalfWidth = halfWidths(splitIndex)/2;
        childCenters = parentCenter + [-childHalfWidth, childHalfWidth];
        childValues = evaluateMargins(normalizedA, childCenters);

        centers(splitIndex) = [];
        halfWidths(splitIndex) = [];
        values(splitIndex) = [];
        centers = [centers, childCenters]; %#ok<AGROW>
        halfWidths = [halfWidths, childHalfWidth, childHalfWidth]; %#ok<AGROW>
        values = [values, childValues]; %#ok<AGROW>
        evaluationCount = evaluationCount+2;
    end

    [lowerBound, bestIndex] = max(values);
    intervalUpperBounds = values + 2*sin(halfWidths/2);
    upperBound = max(intervalUpperBounds);
    bestTheta = mod(centers(bestIndex)+pi, 2*pi)-pi;

    if lowerBound > normalizedTolerance
        candidateClassification = "strict-sectorial";
    elseif lowerBound < -normalizedTolerance
        candidateClassification = "non-sectorial";
    else
        candidateClassification = "boundary";
    end

    isCertified = any(classification == ...
        ["strict-sectorial", "non-sectorial", "boundary"]);
    result = struct( ...
        'classification', classification, ...
        'candidateClassification', candidateClassification, ...
        'isStrictSectorial', classification == "strict-sectorial", ...
        'isBoundary', classification == "boundary", ...
        'isCertified', isCertified, ...
        'floatingPointCertified', false, ...
        'theta', bestTheta, ...
        'margin', lowerBound*scale, ...
        'normalizedMargin', lowerBound, ...
        'lowerBound', lowerBound*scale, ...
        'upperBound', upperBound*scale, ...
        'normalizedLowerBound', lowerBound, ...
        'normalizedUpperBound', upperBound, ...
        'optimalityGap', (upperBound-lowerBound)*scale, ...
        'normalizedOptimalityGap', upperBound-lowerBound, ...
        'tolerance', tolerance, ...
        'normalizedTolerance', normalizedTolerance, ...
        'scale', scale, ...
        'evaluationCount', evaluationCount, ...
        'activeIntervalCount', numel(centers), ...
        'maximumActiveHalfWidth', max(halfWidths), ...
        'stopReason', stopReason, ...
        'initialIntervals', options.InitialIntervals, ...
        'maxEvaluations', options.MaxEvaluations, ...
        'boundScope', "angular-discretization-only", ...
        'method', "adaptive-rotated-Hermitian-envelope-v1");
end

function margins = evaluateMargins(A, theta)
    margins = zeros(size(theta));
    for index = 1:numel(theta)
        rotatedA = exp(-1i*theta(index))*A;
        hermitianPart = (rotatedA+rotatedA')/2;
        eigenvalues = eig(hermitianPart, 'vector');
        margins(index) = min(real(eigenvalues));
    end
end

function [classification, stopReason] = classifyEnvelope(lower, upper, tolerance)
    classification = "indeterminate";
    stopReason = "";

    if lower > tolerance
        classification = "strict-sectorial";
        stopReason = "strict-separation";
    elseif upper < -tolerance
        classification = "non-sectorial";
        stopReason = "negative-global-upper-bound";
    elseif lower >= -tolerance && upper <= tolerance
        classification = "boundary";
        stopReason = "boundary-band";
    end
end

function validateMatrix(A)
    if ~(isnumeric(A) && ismatrix(A) && ~isempty(A) && ...
            size(A, 1) == size(A, 2))
        error('gfm:classifyNumericalRangeAdaptive:InvalidMatrix', ...
            'A must be a nonempty numeric square matrix.');
    end

    if any(~isfinite(A(:)))
        error('gfm:classifyNumericalRangeAdaptive:NonFiniteMatrix', ...
            'A must not contain NaN or Inf values.');
    end
end

function options = validateOptions(options)
    if ~(isstruct(options) && isscalar(options))
        error('gfm:classifyNumericalRangeAdaptive:InvalidOptions', ...
            'Options must be a scalar struct.');
    end

    defaults = struct( ...
        'InitialIntervals', 32, ...
        'MaxEvaluations', 4096, ...
        'OptimalityTol', 1e-10, ...
        'MinHalfWidth', 1e-12, ...
        'RelTol', 1e-8, ...
        'AbsTol', 0);
    allowedFields = fieldnames(defaults);
    suppliedFields = fieldnames(options);
    unknownFields = setdiff(suppliedFields, allowedFields);

    if ~isempty(unknownFields)
        error('gfm:classifyNumericalRangeAdaptive:UnknownOption', ...
            'Unknown option: %s.', unknownFields{1});
    end

    for index = 1:numel(allowedFields)
        fieldName = allowedFields{index};
        if ~isfield(options, fieldName)
            options.(fieldName) = defaults.(fieldName);
        end
    end

    if ~isIntegerScalar(options.InitialIntervals) || ...
            options.InitialIntervals < 4
        error('gfm:classifyNumericalRangeAdaptive:InvalidInitialIntervals', ...
            'InitialIntervals must be an integer greater than or equal to 4.');
    end

    if ~isIntegerScalar(options.MaxEvaluations) || ...
            options.MaxEvaluations < options.InitialIntervals
        error('gfm:classifyNumericalRangeAdaptive:InvalidMaxEvaluations', ...
            'MaxEvaluations must be an integer no smaller than InitialIntervals.');
    end

    if ~isNonnegativeScalar(options.OptimalityTol)
        error('gfm:classifyNumericalRangeAdaptive:InvalidOptimalityTol', ...
            'OptimalityTol must be a finite nonnegative scalar.');
    end

    if ~(isnumeric(options.MinHalfWidth) && isreal(options.MinHalfWidth) && ...
            isscalar(options.MinHalfWidth) && ...
            isfinite(options.MinHalfWidth) && options.MinHalfWidth > 0)
        error('gfm:classifyNumericalRangeAdaptive:InvalidMinHalfWidth', ...
            'MinHalfWidth must be a finite positive scalar.');
    end

    if ~isNonnegativeScalar(options.RelTol) || ...
            ~isNonnegativeScalar(options.AbsTol)
        error('gfm:classifyNumericalRangeAdaptive:InvalidTolerance', ...
            'RelTol and AbsTol must be finite nonnegative scalars.');
    end
end

function tf = isIntegerScalar(value)
    tf = isnumeric(value) && isreal(value) && isscalar(value) && ...
        isfinite(value) && value == floor(value);
end

function tf = isNonnegativeScalar(value)
    tf = isnumeric(value) && isreal(value) && isscalar(value) && ...
        isfinite(value) && value >= 0;
end

function result = makeDegenerateResult(scale, tolerance, options)
    result = struct( ...
        'classification', "degenerate", ...
        'candidateClassification', "degenerate", ...
        'isStrictSectorial', false, ...
        'isBoundary', false, ...
        'isCertified', true, ...
        'floatingPointCertified', false, ...
        'theta', NaN, ...
        'margin', 0, ...
        'normalizedMargin', NaN, ...
        'lowerBound', 0, ...
        'upperBound', 0, ...
        'normalizedLowerBound', NaN, ...
        'normalizedUpperBound', NaN, ...
        'optimalityGap', 0, ...
        'normalizedOptimalityGap', NaN, ...
        'tolerance', tolerance, ...
        'normalizedTolerance', NaN, ...
        'scale', scale, ...
        'evaluationCount', 0, ...
        'activeIntervalCount', 0, ...
        'maximumActiveHalfWidth', NaN, ...
        'stopReason', "degenerate", ...
        'initialIntervals', options.InitialIntervals, ...
        'maxEvaluations', options.MaxEvaluations, ...
        'boundScope', "angular-discretization-only", ...
        'method', "adaptive-rotated-Hermitian-envelope-v1");
end
