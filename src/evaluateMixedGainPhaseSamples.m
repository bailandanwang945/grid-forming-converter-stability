function result = evaluateMixedGainPhaseSamples(converterResponses, ...
        networkResponse, frequenciesHz, conventions, preconditions, options)
%EVALUATEMIXEDGAINPHASESAMPLES Evaluate sampled sufficient conditions.
%   This function implements a conservative strict-sectorial subset of the
%   decentralized mixed small-gain--small-phase condition. A failure means
%   only that the sufficient condition did not confirm the sampled point;
%   it does not imply closed-loop instability.

    if nargin < 6 || isempty(options)
        options = struct();
    end
    options = validateOptions(options);
    frequenciesHz = validateInputs(converterResponses, networkResponse, ...
        frequenciesHz, conventions, preconditions);

    converterCount = numel(converterResponses);
    frequencyCount = numel(frequenciesHz);
    converterMaximumSingularValue = NaN(converterCount, frequencyCount);
    networkMinimumSingularValue = NaN(1, frequencyCount);
    networkConditionNumber = NaN(1, frequencyCount);
    gainMargin = NaN(1, frequencyCount);
    gainStatus = strings(1, frequencyCount);
    converterLowerPhase = NaN(converterCount, frequencyCount);
    converterUpperPhase = NaN(converterCount, frequencyCount);
    networkInverseLowerPhase = NaN(1, frequencyCount);
    networkInverseUpperPhase = NaN(1, frequencyCount);
    upperPhaseMargin = NaN(converterCount, frequencyCount);
    lowerPhaseMargin = NaN(converterCount, frequencyCount);
    converterPhaseSpreadMargin = NaN(1, frequencyCount);
    phaseStatus = strings(1, frequencyCount);
    sampleCoverage = strings(1, frequencyCount);
    activeConstraint = strings(1, frequencyCount);
    reasonCodes = cell(1, frequencyCount);

    identityMatrix = eye(size(networkResponse, 1));
    for frequencyIndex = 1:frequencyCount
        networkMatrix = networkResponse(:, :, frequencyIndex);
        networkSingularValues = svd(networkMatrix);
        networkMinimumSingularValue(frequencyIndex) = ...
            networkSingularValues(end);
        networkConditionNumber(frequencyIndex) = cond(networkMatrix, 2);

        for converterIndex = 1:converterCount
            converterSingularValues = svd( ...
                converterResponses{converterIndex}(:, :, frequencyIndex));
            converterMaximumSingularValue(converterIndex, frequencyIndex) = ...
                converterSingularValues(1);
        end
        maximumConverterGain = max( ...
            converterMaximumSingularValue(:, frequencyIndex));
        gainMargin(frequencyIndex) = ...
            networkMinimumSingularValue(frequencyIndex)-maximumConverterGain;
        gainScale = max(networkMinimumSingularValue(frequencyIndex), ...
            maximumConverterGain);
        gainTolerance = max(options.GainAbsTol, ...
            options.GainRelTol*gainScale);
        gainStatus(frequencyIndex) = classifySignedMargin( ...
            gainMargin(frequencyIndex), gainTolerance);

        [phaseStatus(frequencyIndex), converterLowerPhase(:, frequencyIndex), ...
            converterUpperPhase(:, frequencyIndex), ...
            networkInverseLowerPhase(frequencyIndex), ...
            networkInverseUpperPhase(frequencyIndex), ...
            upperPhaseMargin(:, frequencyIndex), ...
            lowerPhaseMargin(:, frequencyIndex), ...
            converterPhaseSpreadMargin(frequencyIndex), phaseReasons] = ...
            evaluatePhaseCondition(converterResponses, converterCount, ...
                networkMatrix, identityMatrix, frequencyIndex, ...
                networkConditionNumber(frequencyIndex), options);

        [sampleCoverage(frequencyIndex), ...
            activeConstraint(frequencyIndex)] = combineConditions( ...
                gainStatus(frequencyIndex), phaseStatus(frequencyIndex));
        reasonCodes{frequencyIndex} = buildReasonCodes( ...
            gainStatus(frequencyIndex), phaseStatus(frequencyIndex), ...
            phaseReasons);
    end

    if any(sampleCoverage == "uncovered")
        sampledBandStatus = "not-confirmed-on-grid";
    elseif any(sampleCoverage == "indeterminate")
        sampledBandStatus = "indeterminate";
    else
        sampledBandStatus = "confirmed-on-grid";
    end
    theoremStatus = determineTheoremStatus( ...
        sampledBandStatus, preconditions);

    result = struct( ...
        'frequenciesHz', frequenciesHz, ...
        'converterMaximumSingularValue', ...
            converterMaximumSingularValue, ...
        'networkMinimumSingularValue', networkMinimumSingularValue, ...
        'networkConditionNumber', networkConditionNumber, ...
        'gainMargin', gainMargin, ...
        'gainStatus', gainStatus, ...
        'converterLowerPhase', converterLowerPhase, ...
        'converterUpperPhase', converterUpperPhase, ...
        'networkInverseLowerPhase', networkInverseLowerPhase, ...
        'networkInverseUpperPhase', networkInverseUpperPhase, ...
        'upperPhaseMargin', upperPhaseMargin, ...
        'lowerPhaseMargin', lowerPhaseMargin, ...
        'converterPhaseSpreadMargin', converterPhaseSpreadMargin, ...
        'phaseStatus', phaseStatus, ...
        'sampleCoverage', sampleCoverage, ...
        'activeConstraint', activeConstraint, ...
        'reasonCodes', {reasonCodes}, ...
        'sampledBandStatus', sampledBandStatus, ...
        'theoremStatus', theoremStatus, ...
        'conventions', conventions, ...
        'preconditions', preconditions, ...
        'options', options, ...
        'method', "strict-sectorial-mixed-gain-phase-samples-v1", ...
        'interpretationBoundary', ...
            ['Not confirmed by this sufficient condition does not mean ', ...
             'that the closed-loop system is unstable.']);
end

function [status, converterLower, converterUpper, networkLower, ...
        networkUpper, upperMargin, lowerMargin, spreadMargin, reasons] = ...
        evaluatePhaseCondition(converterResponses, converterCount, ...
        networkMatrix, identityMatrix, frequencyIndex, networkCondition, ...
        options)
    converterLower = NaN(converterCount, 1);
    converterUpper = NaN(converterCount, 1);
    upperMargin = NaN(converterCount, 1);
    lowerMargin = NaN(converterCount, 1);
    networkLower = NaN;
    networkUpper = NaN;
    spreadMargin = NaN;
    reasons = strings(0, 1);

    if ~isfinite(networkCondition) || ...
            networkCondition > options.NetworkConditionNumberLimit
        status = "indeterminate";
        reasons(end+1) = "ill-conditioned-network";
        return;
    end

    converterResults = cell(converterCount, 1);
    for converterIndex = 1:converterCount
        converterResults{converterIndex} = ...
            computeStrictSectorialPhaseInterval( ...
                converterResponses{converterIndex}(:, :, frequencyIndex), ...
                options.PhaseOptions);
    end
    networkInverse = networkMatrix\identityMatrix;
    networkResult = computeStrictSectorialPhaseInterval( ...
        networkInverse, options.PhaseOptions);

    statuses = strings(converterCount+1, 1);
    for converterIndex = 1:converterCount
        statuses(converterIndex) = converterResults{converterIndex}.status;
    end
    statuses(end) = networkResult.status;
    converterStatuses = statuses(1:converterCount);
    if any(converterStatuses == "not-applicable")
        status = "fail";
        reasons(end+1) = "converter-nonsectorial";
        return;
    end
    if statuses(end) == "not-applicable"
        status = "fail";
        reasons(end+1) = "network-inverse-nonsectorial";
        return;
    end
    if any(statuses ~= "resolved")
        status = "indeterminate";
        reasons(end+1) = "sectoriality-or-phase-indeterminate";
        return;
    end

    for converterIndex = 1:converterCount
        converterLower(converterIndex) = ...
            converterResults{converterIndex}.lowerPhase;
        converterUpper(converterIndex) = ...
            converterResults{converterIndex}.upperPhase;
    end
    networkLower = networkResult.lowerPhase;
    networkUpper = networkResult.upperPhase;
    upperMargin = pi-networkUpper-converterUpper;
    lowerMargin = converterLower+pi+networkLower;
    spreadMargin = pi-(max(converterUpper)-min(converterLower));
    allMargins = [upperMargin; lowerMargin; spreadMargin];

    if all(allMargins > options.PhaseAbsTol)
        status = "pass";
        reasons(end+1) = "phase-pass";
    elseif any(allMargins < -options.PhaseAbsTol)
        status = "fail";
        if any(upperMargin < -options.PhaseAbsTol)
            reasons(end+1) = "upper-phase-overlap";
        end
        if any(lowerMargin < -options.PhaseAbsTol)
            reasons(end+1) = "lower-phase-overlap";
        end
        if spreadMargin < -options.PhaseAbsTol
            reasons(end+1) = "converter-phase-spread-overlap";
        end
    else
        status = "indeterminate";
        reasons(end+1) = "phase-boundary-indeterminate";
    end
end

function status = classifySignedMargin(margin, tolerance)
    if margin > tolerance
        status = "pass";
    elseif margin < -tolerance
        status = "fail";
    else
        status = "indeterminate";
    end
end

function [coverage, activeConstraint] = combineConditions( ...
        gainStatus, phaseStatus)
    if gainStatus == "pass" && phaseStatus == "pass"
        coverage = "both-pass";
        activeConstraint = "both";
    elseif gainStatus == "pass"
        coverage = "gain-pass";
        activeConstraint = "gain";
    elseif phaseStatus == "pass"
        coverage = "phase-pass";
        activeConstraint = "phase";
    elseif gainStatus == "fail" && phaseStatus == "fail"
        coverage = "uncovered";
        activeConstraint = "gain-and-phase";
    else
        coverage = "indeterminate";
        activeConstraint = "numerical-boundary-or-prerequisite";
    end
end

function reasons = buildReasonCodes(gainStatus, phaseStatus, phaseReasons)
    reasons = strings(0, 1);
    if gainStatus == "indeterminate"
        reasons(end+1) = "gain-boundary-indeterminate";
    else
        reasons(end+1) = "gain-"+gainStatus;
    end
    if isempty(phaseReasons)
        reasons(end+1) = "phase-"+phaseStatus;
    else
        reasons = [reasons; phaseReasons];
    end
end

function theoremStatus = determineTheoremStatus( ...
        sampledBandStatus, preconditions)
    if sampledBandStatus == "not-confirmed-on-grid"
        theoremStatus = "not-confirmed-by-sufficient-condition";
        return;
    end
    requiredNames = theoremPreconditionNames();
    values = false(size(requiredNames));
    for index = 1:numel(requiredNames)
        values(index) = preconditions.(requiredNames(index));
    end
    if sampledBandStatus == "confirmed-on-grid" && all(values)
        theoremStatus = "confirmed-by-sufficient-condition";
    else
        theoremStatus = "indeterminate";
    end
end

function frequenciesHz = validateInputs(converterResponses, ...
        networkResponse, frequenciesHz, conventions, preconditions)
    if ~(iscell(converterResponses) && ~isempty(converterResponses))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidConverters', ...
            'converterResponses must be a nonempty cell array.');
    end
    if ~(isnumeric(frequenciesHz) && isreal(frequenciesHz) && ...
            isvector(frequenciesHz) && ~isempty(frequenciesHz) && ...
            all(isfinite(frequenciesHz)) && all(frequenciesHz >= 0))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidFrequencies', ...
            'frequenciesHz must be a finite nonnegative real vector.');
    end
    frequenciesHz = frequenciesHz(:).';
    if any(diff(frequenciesHz) <= 0)
        error('gfm:evaluateMixedGainPhaseSamples:InvalidFrequencies', ...
            'frequenciesHz must be strictly increasing.');
    end
    frequencyCount = numel(frequenciesHz);

    converterDimension = 0;
    for index = 1:numel(converterResponses)
        response = converterResponses{index};
        validateResponseArray(response, frequencyCount, 'converter');
        converterDimension = converterDimension+size(response, 1);
    end
    validateResponseArray(networkResponse, frequencyCount, 'network');
    if size(networkResponse, 1) ~= converterDimension
        error('gfm:evaluateMixedGainPhaseSamples:DimensionMismatch', ...
            'Network dimension must equal the sum of converter dimensions.');
    end
    validateConventions(conventions);
    validatePreconditions(preconditions);
end

function validateResponseArray(response, frequencyCount, name)
    if ~(isnumeric(response) && ~isempty(response) && ...
            size(response, 1) == size(response, 2) && ...
            size(response, 3) == frequencyCount && ...
            all(isfinite(response(:))))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidResponse', ...
            '%s response must be a finite square matrix array.', name);
    end
end

function validateConventions(conventions)
    if ~(isstruct(conventions) && isscalar(conventions))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidConventions', ...
            'conventions must be a scalar struct.');
    end
    requiredNames = ["frameConventionId", "currentDirection", ...
        "powerDirection", "sBase", "vBase", "fBase", ...
        "matrixType", "globalFrameId"];
    if ~all(isfield(conventions, requiredNames))
        error('gfm:evaluateMixedGainPhaseSamples:MissingConvention', ...
            'All coordinate, direction, base, and matrix conventions are required.');
    end
    baseNames = ["sBase", "vBase", "fBase"];
    for index = 1:numel(baseNames)
        value = conventions.(baseNames(index));
        if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
                isfinite(value) && value > 0)
            error('gfm:evaluateMixedGainPhaseSamples:InvalidConvention', ...
                '%s must be a finite positive scalar.', baseNames(index));
        end
    end
    if string(conventions.matrixType) ~= "admittance"
        error('gfm:evaluateMixedGainPhaseSamples:InvalidMatrixType', ...
            'This evaluator currently accepts admittance responses only.');
    end
end

function validatePreconditions(preconditions)
    if ~(isstruct(preconditions) && isscalar(preconditions))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidPreconditions', ...
            'preconditions must be a scalar struct.');
    end
    names = theoremPreconditionNames();
    if ~all(isfield(preconditions, names))
        error('gfm:evaluateMixedGainPhaseSamples:MissingPrecondition', ...
            'All theorem preconditions must be explicitly supplied.');
    end
    for index = 1:numel(names)
        value = preconditions.(names(index));
        if ~(islogical(value) && isscalar(value))
            error('gfm:evaluateMixedGainPhaseSamples:InvalidPrecondition', ...
                '%s must be a logical scalar.', names(index));
        end
    end
end

function names = theoremPreconditionNames()
    names = ["openLoopStable", "realRationalProper", ...
        "transformationWellDefined", "networkInverseStable", ...
        "noRhpCancellation", "endpointsCovered", ...
        "fullFrequencyCoverage"];
end

function options = validateOptions(options)
    if ~(isstruct(options) && isscalar(options))
        error('gfm:evaluateMixedGainPhaseSamples:InvalidOptions', ...
            'options must be a scalar struct.');
    end
    defaults = struct( ...
        'GainRelTol', 1e-10, ...
        'GainAbsTol', 0, ...
        'PhaseAbsTol', 1e-10, ...
        'NetworkConditionNumberLimit', 1e12, ...
        'PhaseOptions', struct());
    names = fieldnames(defaults);
    unknownNames = setdiff(fieldnames(options), names);
    if ~isempty(unknownNames)
        error('gfm:evaluateMixedGainPhaseSamples:UnknownOption', ...
            'Unknown option: %s.', unknownNames{1});
    end
    for index = 1:numel(names)
        name = names{index};
        if ~isfield(options, name)
            options.(name) = defaults.(name);
        end
    end
    validateNonnegativeOption(options.GainRelTol, 'GainRelTol');
    validateNonnegativeOption(options.GainAbsTol, 'GainAbsTol');
    validateNonnegativeOption(options.PhaseAbsTol, 'PhaseAbsTol');
    if ~(isnumeric(options.NetworkConditionNumberLimit) && ...
            isreal(options.NetworkConditionNumberLimit) && ...
            isscalar(options.NetworkConditionNumberLimit) && ...
            isfinite(options.NetworkConditionNumberLimit) && ...
            options.NetworkConditionNumberLimit > 0)
        error('gfm:evaluateMixedGainPhaseSamples:InvalidOption', ...
            'NetworkConditionNumberLimit must be positive and finite.');
    end
end

function validateNonnegativeOption(value, name)
    if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
            isfinite(value) && value >= 0)
        error('gfm:evaluateMixedGainPhaseSamples:InvalidOption', ...
            '%s must be finite and nonnegative.', name);
    end
end
