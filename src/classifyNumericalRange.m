function result = classifyNumericalRange(A, options)
%CLASSIFYNUMERICALRANGE Classify the numerical range relative to the origin.
%   RESULT = CLASSIFYNUMERICALRANGE(A) searches for a rotation angle THETA
%   that maximizes the smallest eigenvalue of
%
%       H_THETA(A) = (exp(-1i*THETA)*A + exp(1i*THETA)*A')/2.
%
%   A positive evaluated margin gives a strict separation certificate.
%   A uniform-grid Lipschitz bound is used to obtain an upper bound on the
%   unknown global maximum. Results that cannot be certified are reported
%   as indeterminate rather than forced into a geometric class.
%
%   RESULT = CLASSIFYNUMERICALRANGE(A, OPTIONS) accepts a scalar struct:
%       NumAngles - coarse angular grid size, default 720
%       RelTol    - relative classification tolerance, default 1e-10
%       AbsTol    - absolute classification tolerance, default 0
%       Refine    - refine the best grid interval with fminbnd, default true
%
%   This function does not distinguish semi-sectorial from
%   quasi-sectorial matrices and does not determine closed-loop stability.

    if nargin < 2 || isempty(options)
        options = struct();
    end

    validateMatrix(A);
    options = validateOptions(options);
    A = double(A);

    scale = norm(A, 2);
    tolerance = max(options.AbsTol, options.RelTol * scale);

    if scale <= options.AbsTol
        result = makeResult("degenerate", "degenerate", false, false, ...
            true, NaN, 0, 0, 0, tolerance, scale, options, false, false, NaN);
        return;
    end

    angleStep = 2*pi/options.NumAngles;
    thetaGrid = -pi + (0:options.NumAngles-1)*angleStep;
    margins = zeros(size(thetaGrid));

    for k = 1:numel(thetaGrid)
        margins(k) = separationMargin(A, thetaGrid(k));
    end

    [gridBestMargin, bestIndex] = max(margins);
    bestMargin = gridBestMargin;
    bestTheta = thetaGrid(bestIndex);
    refinementAttempted = false;
    refinementAccepted = false;
    refinementExitFlag = NaN;

    if options.Refine
        refinementAttempted = true;
        lowerTheta = bestTheta - angleStep;
        upperTheta = bestTheta + angleStep;
        optimizerOptions = optimset('Display', 'off', 'TolX', 1e-12);
        [candidateTheta, negativeMargin, refinementExitFlag] = fminbnd( ...
            @(theta) -separationMargin(A, theta), ...
            lowerTheta, upperTheta, optimizerOptions);
        candidateMargin = -negativeMargin;

        if candidateMargin > bestMargin
            bestTheta = candidateTheta;
            bestMargin = candidateMargin;
            refinementAccepted = true;
        end
    end

    bestTheta = mod(bestTheta + pi, 2*pi) - pi;
    normalizedMargin = bestMargin/scale;
    gridErrorBound = 2*sin(angleStep/4)*scale;
    lowerBound = bestMargin;
    upperBound = max(bestMargin, gridBestMargin + gridErrorBound);

    if bestMargin > tolerance
        candidateClassification = "strict-sectorial";
    elseif bestMargin < -tolerance
        candidateClassification = "non-sectorial";
    else
        candidateClassification = "boundary";
    end

    if lowerBound > tolerance
        classification = "strict-sectorial";
        isStrictSectorial = true;
        isBoundary = false;
        isCertified = true;
    elseif upperBound < -tolerance
        classification = "non-sectorial";
        isStrictSectorial = false;
        isBoundary = false;
        isCertified = true;
    elseif lowerBound >= -tolerance && upperBound <= tolerance
        classification = "boundary";
        isStrictSectorial = false;
        isBoundary = true;
        isCertified = true;
    else
        classification = "indeterminate";
        isStrictSectorial = false;
        isBoundary = false;
        isCertified = false;
    end

    result = makeResult(classification, candidateClassification, ...
        isStrictSectorial, isBoundary, isCertified, bestTheta, bestMargin, ...
        lowerBound, upperBound, tolerance, scale, options, ...
        refinementAttempted, refinementAccepted, refinementExitFlag);
    result.normalizedMargin = normalizedMargin;
end

function margin = separationMargin(A, theta)
    rotatedA = exp(-1i*theta)*A;
    hermitianPart = (rotatedA + rotatedA')/2;
    eigenvalues = eig(hermitianPart, 'vector');
    margin = min(real(eigenvalues));
end

function validateMatrix(A)
    if ~(isnumeric(A) && ismatrix(A) && ~isempty(A) && size(A, 1) == size(A, 2))
        error('gfm:classifyNumericalRange:InvalidMatrix', ...
            'A must be a nonempty numeric square matrix.');
    end

    if any(~isfinite(A(:)))
        error('gfm:classifyNumericalRange:NonFiniteMatrix', ...
            'A must not contain NaN or Inf values.');
    end
end

function options = validateOptions(options)
    if ~(isstruct(options) && isscalar(options))
        error('gfm:classifyNumericalRange:InvalidOptions', ...
            'Options must be a scalar struct.');
    end

    defaults = struct( ...
        'NumAngles', 720, ...
        'RelTol', 1e-10, ...
        'AbsTol', 0, ...
        'Refine', true);
    allowedFields = fieldnames(defaults);
    suppliedFields = fieldnames(options);
    unknownFields = setdiff(suppliedFields, allowedFields);

    if ~isempty(unknownFields)
        error('gfm:classifyNumericalRange:UnknownOption', ...
            'Unknown option: %s.', unknownFields{1});
    end

    for k = 1:numel(allowedFields)
        fieldName = allowedFields{k};
        if ~isfield(options, fieldName)
            options.(fieldName) = defaults.(fieldName);
        end
    end

    if ~(isnumeric(options.NumAngles) && isreal(options.NumAngles) && ...
            isscalar(options.NumAngles) && ...
            isfinite(options.NumAngles) && options.NumAngles >= 16 && ...
            options.NumAngles == floor(options.NumAngles))
        error('gfm:classifyNumericalRange:InvalidNumAngles', ...
            'NumAngles must be an integer greater than or equal to 16.');
    end

    if ~(isnumeric(options.RelTol) && isreal(options.RelTol) && ...
            isscalar(options.RelTol) && ...
            isfinite(options.RelTol) && options.RelTol >= 0 && ...
            isnumeric(options.AbsTol) && isreal(options.AbsTol) && ...
            isscalar(options.AbsTol) && ...
            isfinite(options.AbsTol) && options.AbsTol >= 0)
        error('gfm:classifyNumericalRange:InvalidTolerance', ...
            'RelTol and AbsTol must be finite nonnegative scalars.');
    end

    if ~(islogical(options.Refine) && isscalar(options.Refine))
        error('gfm:classifyNumericalRange:InvalidRefine', ...
            'Refine must be a logical scalar.');
    end
end

function result = makeResult(classification, candidateClassification, ...
        isStrictSectorial, isBoundary, isCertified, theta, margin, ...
        lowerBound, upperBound, tolerance, scale, options, ...
        refinementAttempted, refinementAccepted, refinementExitFlag)
    if scale > 0
        normalizedMargin = margin/scale;
        normalizedLowerBound = lowerBound/scale;
        normalizedUpperBound = upperBound/scale;
    else
        normalizedMargin = NaN;
        normalizedLowerBound = NaN;
        normalizedUpperBound = NaN;
    end

    result = struct( ...
        'classification', classification, ...
        'candidateClassification', candidateClassification, ...
        'isStrictSectorial', isStrictSectorial, ...
        'isBoundary', isBoundary, ...
        'isCertified', isCertified, ...
        'theta', theta, ...
        'margin', margin, ...
        'normalizedMargin', normalizedMargin, ...
        'lowerBound', lowerBound, ...
        'upperBound', upperBound, ...
        'normalizedLowerBound', normalizedLowerBound, ...
        'normalizedUpperBound', normalizedUpperBound, ...
        'optimalityGap', upperBound-lowerBound, ...
        'tolerance', tolerance, ...
        'scale', scale, ...
        'numAngles', options.NumAngles, ...
        'refinementAttempted', refinementAttempted, ...
        'refinementAccepted', refinementAccepted, ...
        'refinementExitFlag', refinementExitFlag, ...
        'method', "rotated-Hermitian-separation-bounds-v2");
end
