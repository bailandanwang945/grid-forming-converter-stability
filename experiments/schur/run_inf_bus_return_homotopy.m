function summary = run_inf_bus_return_homotopy(caseName)
%RUN_INF_BUS_RETURN_HOMOTOPY Scan exact loop-closure singularity margins.
%   The return matrix is R_tau = I + tau*Jc/Jnet. A zero singular value on
%   the imaginary axis marks a possible change in the closed-loop zero
%   count as the converter-network feedback is closed from tau=0 to tau=1.

    arguments
        caseName (1, 1) string {mustBeMember(caseName, ["stable", "unstable"])}
    end

    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    workspacePath = fullfile(projectRoot, 'results', 'schur', caseName, ...
        'schur_workspace.mat');
    outputRoot = fullfile(projectRoot, 'results', 'schur', caseName);
    assert(isfile(workspacePath), 'ReturnHomotopy:MissingSchurWorkspace', ...
        'Run the corresponding Schur analysis first.');

    data = load(workspacePath, 'converterMatrix', 'networkMatrix');
    frequenciesHz = logspace(log10(1e-3), log10(1e4), 2000).';
    tauGrid = linspace(0, 1, 1001);
    minimumMarginByFrequency = inf(size(frequenciesHz));
    minimizingTauByFrequency = zeros(size(frequenciesHz));
    determinantMagnitudeAtMinimum = inf(size(frequenciesHz));

    for frequencyIndex = 1:numel(frequenciesHz)
        angularFrequency = 2*pi*frequenciesHz(frequencyIndex);
        converterAtFrequency = evalfr(data.converterMatrix, 1i*angularFrequency);
        networkAtFrequency = evalfr(data.networkMatrix, 1i*angularFrequency);
        loopAtFrequency = converterAtFrequency / networkAtFrequency;

        for tauIndex = 1:numel(tauGrid)
            returnMatrix = eye(2) + tauGrid(tauIndex) * loopAtFrequency;
            singularValues = svd(returnMatrix);
            normalizedMargin = singularValues(end) / max(1, singularValues(1));
            if normalizedMargin < minimumMarginByFrequency(frequencyIndex)
                minimumMarginByFrequency(frequencyIndex) = normalizedMargin;
                minimizingTauByFrequency(frequencyIndex) = tauGrid(tauIndex);
                determinantMagnitudeAtMinimum(frequencyIndex) = abs(det(returnMatrix));
            end
        end
    end

    [globalMinimumMargin, minimumIndex] = min(minimumMarginByFrequency);
    networkZerosHz = tzero(ss(data.networkMatrix)) / (2*pi);
    converterPolesHz = pole(ss(data.converterMatrix)) / (2*pi);

    summary = struct( ...
        'caseName', caseName, ...
        'tauGridPoints', numel(tauGrid), ...
        'frequencyGridPoints', numel(frequenciesHz), ...
        'minimumNormalizedReturnMargin', globalMinimumMargin, ...
        'minimumMarginHz', frequenciesHz(minimumIndex), ...
        'minimumMarginTau', minimizingTauByFrequency(minimumIndex), ...
        'determinantMagnitudeAtMinimum', ...
            determinantMagnitudeAtMinimum(minimumIndex), ...
        'maximumRealNetworkZeroHz', maximumRealPart(networkZerosHz), ...
        'maximumRealConverterPoleHz', maximumRealPart(converterPolesHz), ...
        'openLoopFactorsStable', maximumRealPart(networkZerosHz) <= 1e-6 && ...
            maximumRealPart(converterPolesHz) <= 1e-6);

    homotopyTable = table( ...
        frequenciesHz, minimumMarginByFrequency, minimizingTauByFrequency, ...
        determinantMagnitudeAtMinimum, ...
        'VariableNames', {'frequency_Hz', 'minimum_normalized_return_margin', ...
        'minimizing_tau', 'determinant_magnitude_at_minimum'});
    writetable(homotopyTable, fullfile(outputRoot, 'return_homotopy.csv'));
    writelines(jsonencode(summary, PrettyPrint=true), ...
        fullfile(outputRoot, 'return_homotopy_summary.json'));

    fprintf(['HOMOTOPY case=%s margin=%.9g tau=%.6g f=%.9gHz ', ...
        'det=%.9g open_loop_stable=%d\n'], ...
        caseName, globalMinimumMargin, minimizingTauByFrequency(minimumIndex), ...
        frequenciesHz(minimumIndex), determinantMagnitudeAtMinimum(minimumIndex), ...
        summary.openLoopFactorsStable);
end

function value = maximumRealPart(numbers)
    if isempty(numbers)
        value = -Inf;
    else
        value = max(real(numbers));
    end
end
