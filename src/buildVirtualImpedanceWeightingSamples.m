function result = buildVirtualImpedanceWeightingSamples( ...
        frequenciesHz, configuration)
%BUILDVIRTUALIMPEDANCEWEIGHTINGSAMPLES Build dq virtual-impedance samples.
%   The returned weighting matrix follows the author's global synchronous
%   dq form
%
%       [sL+R, -w0*L; w0*L, sL+R] / normalization,
%
%   where L = X/w0. When NormalizeAtBase is true, normalization is
%   abs(R+1i*X), matching the released Cifelli--Anta scripts.

    frequenciesHz = validateFrequencies(frequenciesHz);
    configuration = validateConfiguration(configuration);

    baseAngularFrequency = double(configuration.BaseAngularFrequency);
    resistance = double(configuration.VirtualResistance);
    reactance = double(configuration.VirtualReactance);
    inductance = reactance/baseAngularFrequency;
    if configuration.NormalizeAtBase
        normalization = hypot(resistance, reactance);
        if normalization == 0
            error('gfm:buildVirtualImpedanceWeightingSamples:ZeroNormalization', ...
                'R and X cannot both be zero when normalization is enabled.');
        end
    else
        normalization = 1;
    end

    frequencyCount = numel(frequenciesHz);
    responses = complex(zeros(2, 2, frequencyCount));
    for index = 1:frequencyCount
        s = 1i*2*pi*frequenciesHz(index);
        diagonalEntry = s*inductance+resistance;
        responses(:, :, index) = [ ...
            diagonalEntry, -reactance; ...
            reactance, diagonalEntry]/normalization;
    end

    result = struct( ...
        'responses', responses, ...
        'frequenciesHz', frequenciesHz, ...
        'inductance', inductance, ...
        'normalization', normalization, ...
        'configuration', configuration, ...
        'method', "dq-virtual-impedance-weighting-v1");
end

function frequenciesHz = validateFrequencies(frequenciesHz)
    if ~(isnumeric(frequenciesHz) && isreal(frequenciesHz) && ...
            isvector(frequenciesHz) && ~isempty(frequenciesHz) && ...
            all(isfinite(frequenciesHz)) && all(frequenciesHz >= 0))
        error('gfm:buildVirtualImpedanceWeightingSamples:InvalidFrequencies', ...
            'frequenciesHz must be a finite nonnegative real vector.');
    end
    frequenciesHz = double(frequenciesHz(:).');
    if any(diff(frequenciesHz) <= 0)
        error('gfm:buildVirtualImpedanceWeightingSamples:InvalidFrequencies', ...
            'frequenciesHz must be strictly increasing.');
    end
end

function configuration = validateConfiguration(configuration)
    if ~(isstruct(configuration) && isscalar(configuration))
        error('gfm:buildVirtualImpedanceWeightingSamples:InvalidConfiguration', ...
            'configuration must be a scalar struct.');
    end
    requiredNames = {'BaseAngularFrequency', 'VirtualResistance', ...
        'VirtualReactance', 'NormalizeAtBase'};
    actualNames = fieldnames(configuration);
    missingNames = setdiff(requiredNames, actualNames);
    unknownNames = setdiff(actualNames, requiredNames);
    if ~isempty(missingNames)
        error('gfm:buildVirtualImpedanceWeightingSamples:MissingField', ...
            'Missing configuration field: %s.', missingNames{1});
    end
    if ~isempty(unknownNames)
        error('gfm:buildVirtualImpedanceWeightingSamples:UnknownField', ...
            'Unknown configuration field: %s.', unknownNames{1});
    end
    validateFiniteRealScalar(configuration.BaseAngularFrequency, ...
        'BaseAngularFrequency', true);
    validateFiniteRealScalar(configuration.VirtualResistance, ...
        'VirtualResistance', false);
    validateFiniteRealScalar(configuration.VirtualReactance, ...
        'VirtualReactance', false);
    if ~(islogical(configuration.NormalizeAtBase) && ...
            isscalar(configuration.NormalizeAtBase))
        error('gfm:buildVirtualImpedanceWeightingSamples:InvalidField', ...
            'NormalizeAtBase must be a logical scalar.');
    end
end

function validateFiniteRealScalar(value, name, mustBePositive)
    isValid = isnumeric(value) && isreal(value) && isscalar(value) && ...
        isfinite(value);
    if mustBePositive
        isValid = isValid && value > 0;
    end
    if ~isValid
        error('gfm:buildVirtualImpedanceWeightingSamples:InvalidField', ...
            '%s must be a finite real scalar with the required sign.', name);
    end
end
