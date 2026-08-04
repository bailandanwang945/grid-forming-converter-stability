function result = computeStrictSectorialPhaseInterval(A, options)
%COMPUTESTRICTSECTORIALPHASEINTERVAL Compute canonical matrix phases.
%   RESULT = COMPUTESTRICTSECTORIALPHASEINTERVAL(A) computes the phase
%   interval of a matrix only when strict sectoriality is certified. It
%   first selects THETA such that B = exp(-1i*THETA)*A has positive
%   definite Hermitian part H. Writing B = H + 1i*G, the generalized
%   eigenvalues of (G,H) are real and give phases atan(lambda) relative to
%   THETA. This is the sectorial congruence definition of matrix phases,
%   not the angles of matrix entries or ordinary eigenvalues.
%
%   Quasi-sectorial and semi-sectorial matrices are intentionally not
%   handled by this conservative function. Indeterminate classification or
%   ill-conditioned phase extraction is reported as numerical-pending.

    if nargin < 2 || isempty(options)
        options = struct();
    end

    validateMatrix(A);
    options = validateOptions(options);
    A = double(A);
    inputScale = max([abs(real(A(:))); abs(imag(A(:)))]);
    if inputScale == 0
        scaledA = A;
        classifierOptions = options.ClassifierOptions;
    else
        scaledA = A/inputScale;
        classifierOptions = options.ClassifierOptions;
        scaledAbsTol = classifierOptions.AbsTol/inputScale;
        classifierOptions.AbsTol = min(scaledAbsTol, realmax('double'));
    end

    classification = classifyNumericalRange(scaledA, classifierOptions);
    normalizedDiagnostics = captureNormalizedDiagnostics(classification);
    classification = restoreClassificationScale(classification, inputScale);
    classification.normalizedDiagnostics = normalizedDiagnostics;
    classification.dimensionalDiagnosticOverflow = any(~isfinite([ ...
        classification.margin, classification.lowerBound, ...
        classification.upperBound, classification.optimalityGap, ...
        classification.tolerance, classification.scale]));
    if classification.classification == "indeterminate"
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "classification-indeterminate", inputScale);
        return;
    end
    if classification.classification ~= "strict-sectorial"
        result = makeUnavailableResult(classification, size(A, 1), ...
            "not-applicable", classification.classification, inputScale);
        return;
    end

    theta = classification.theta;
    rotatedMatrix = exp(-1i*theta)*scaledA;
    hermitianPart = (rotatedMatrix+rotatedMatrix')/2;
    quadratureHermitianPart = (rotatedMatrix-rotatedMatrix')/(2i);
    hermitianPart = (hermitianPart+hermitianPart')/2;
    quadratureHermitianPart = ...
        (quadratureHermitianPart+quadratureHermitianPart')/2;
    if any(~isfinite(rotatedMatrix(:))) || ...
            any(~isfinite(hermitianPart(:))) || ...
            any(~isfinite(quadratureHermitianPart(:)))
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "nonfinite-intermediate", inputScale);
        return;
    end

    [~, positiveDefiniteFlag] = chol(hermitianPart);
    if positiveDefiniteFlag ~= 0
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", ...
            "rotated-hermitian-not-positive-definite", inputScale);
        return;
    end

    hermitianConditionNumber = cond(hermitianPart, 2);
    if ~isfinite(hermitianConditionNumber) || ...
            hermitianConditionNumber > options.MaxHermitianConditionNumber
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "ill-conditioned-hermitian-part", inputScale);
        result.hermitianConditionNumber = hermitianConditionNumber;
        return;
    end

    tangentValues = eig( ...
        quadratureHermitianPart, hermitianPart, 'vector');
    if any(~isfinite(tangentValues))
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "nonfinite-intermediate", inputScale);
        result.hermitianConditionNumber = hermitianConditionNumber;
        return;
    end
    tangentScale = max(1, max(abs(tangentValues)));
    normalizedImaginaryResidual = ...
        max(abs(imag(tangentValues)))/tangentScale;
    if normalizedImaginaryResidual > options.MaxRelativeImaginaryResidual
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "complex-generalized-eigenvalues", inputScale);
        result.hermitianConditionNumber = hermitianConditionNumber;
        result.normalizedImaginaryResidual = normalizedImaginaryResidual;
        return;
    end

    relativePhases = sort(atan(real(tangentValues)), 'ascend');
    unwrappedPhases = theta + relativePhases;
    if any(~isfinite(unwrappedPhases))
        result = makeUnavailableResult(classification, size(A, 1), ...
            "numerical-pending", "nonfinite-intermediate", inputScale);
        result.hermitianConditionNumber = hermitianConditionNumber;
        return;
    end
    intervalCenter = (unwrappedPhases(1)+unwrappedPhases(end))/2;
    branchShift = 2*pi*floor((intervalCenter+pi)/(2*pi));
    unwrappedPhases = unwrappedPhases-branchShift;
    lowerPhase = unwrappedPhases(1);
    upperPhase = unwrappedPhases(end);

    result = struct( ...
        'status', "resolved", ...
        'reason', "strict-sectorial", ...
        'classification', classification, ...
        'phases', sort(unwrappedPhases, 'descend'), ...
        'lowerPhase', lowerPhase, ...
        'upperPhase', upperPhase, ...
        'phaseWidth', upperPhase-lowerPhase, ...
        'branchCenter', (lowerPhase+upperPhase)/2, ...
        'rotationTheta', theta, ...
        'hermitianConditionNumber', hermitianConditionNumber, ...
        'normalizedImaginaryResidual', normalizedImaginaryResidual, ...
        'inputScale', inputScale, ...
        'method', "strict-sectorial-generalized-HG-v1");
end

function diagnostics = captureNormalizedDiagnostics(classification)
    diagnostics = struct( ...
        'margin', classification.margin, ...
        'lowerBound', classification.lowerBound, ...
        'upperBound', classification.upperBound, ...
        'optimalityGap', classification.optimalityGap, ...
        'tolerance', classification.tolerance, ...
        'scale', classification.scale);
end

function classification = restoreClassificationScale( ...
        classification, inputScale)
    dimensionalNames = {'margin', 'lowerBound', 'upperBound', ...
        'optimalityGap', 'tolerance', 'scale'};
    for index = 1:numel(dimensionalNames)
        name = dimensionalNames{index};
        classification.(name) = classification.(name)*inputScale;
    end
    classification.inputNormalizationScale = inputScale;
end

function validateMatrix(A)
    if ~(isnumeric(A) && ismatrix(A) && ~isempty(A) && ...
            size(A, 1) == size(A, 2))
        error('gfm:computeStrictSectorialPhaseInterval:InvalidMatrix', ...
            'A must be a nonempty numeric square matrix.');
    end
    if any(~isfinite(A(:)))
        error('gfm:computeStrictSectorialPhaseInterval:NonFiniteMatrix', ...
            'A must not contain NaN or Inf values.');
    end
end

function options = validateOptions(options)
    if ~(isstruct(options) && isscalar(options))
        error('gfm:computeStrictSectorialPhaseInterval:InvalidOptions', ...
            'Options must be a scalar struct.');
    end

    defaults = struct( ...
        'ClassifierOptions', struct('NumAngles', 1440, ...
            'RelTol', 1e-10, 'AbsTol', 0, 'Refine', true), ...
        'MaxHermitianConditionNumber', 1e12, ...
        'MaxRelativeImaginaryResidual', 1e-10);
    names = fieldnames(defaults);
    unknownNames = setdiff(fieldnames(options), names);
    if ~isempty(unknownNames)
        error('gfm:computeStrictSectorialPhaseInterval:UnknownOption', ...
            'Unknown option: %s.', unknownNames{1});
    end
    for index = 1:numel(names)
        name = names{index};
        if ~isfield(options, name)
            options.(name) = defaults.(name);
        end
    end

    validatePositiveScalar(options.MaxHermitianConditionNumber, ...
        'MaxHermitianConditionNumber');
    validateNonnegativeScalar(options.MaxRelativeImaginaryResidual, ...
        'MaxRelativeImaginaryResidual');
end

function validatePositiveScalar(value, name)
    if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
            isfinite(value) && value > 0)
        error('gfm:computeStrictSectorialPhaseInterval:InvalidOption', ...
            '%s must be a finite positive scalar.', name);
    end
end

function validateNonnegativeScalar(value, name)
    if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
            isfinite(value) && value >= 0)
        error('gfm:computeStrictSectorialPhaseInterval:InvalidOption', ...
            '%s must be a finite nonnegative scalar.', name);
    end
end

function result = makeUnavailableResult(classification, matrixSize, ...
        status, reason, inputScale)
    result = struct( ...
        'status', status, ...
        'reason', reason, ...
        'classification', classification, ...
        'phases', NaN(matrixSize, 1), ...
        'lowerPhase', NaN, ...
        'upperPhase', NaN, ...
        'phaseWidth', NaN, ...
        'branchCenter', NaN, ...
        'rotationTheta', classification.theta, ...
        'hermitianConditionNumber', NaN, ...
        'normalizedImaginaryResidual', NaN, ...
        'inputScale', inputScale, ...
        'method', "strict-sectorial-generalized-HG-v1");
end
