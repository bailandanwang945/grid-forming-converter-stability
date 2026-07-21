function summary = run_inf_bus_zero_continuation(caseName)
%RUN_INF_BUS_ZERO_CONTINUATION Track characteristic zeros during loop closure.

    arguments
        caseName (1, 1) string {mustBeMember(caseName, ["stable", "unstable"])}
    end

    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    workspacePath = fullfile(projectRoot, 'results', 'schur', caseName, ...
        'schur_workspace.mat');
    outputRoot = fullfile(projectRoot, 'results', 'schur', caseName);
    assert(isfile(workspacePath), 'ZeroContinuation:MissingWorkspace', ...
        'Run the corresponding Schur analysis first.');

    data = load(workspacePath, 'converterMatrix', 'networkMatrix');
    tauGrid = linspace(0, 1, 201).';
    dominantRealHz = zeros(size(tauGrid));
    dominantImaginaryHz = zeros(size(tauGrid));

    for index = 1:numel(tauGrid)
        dominantZero = dominantZeroAtTau( ...
            data.converterMatrix, data.networkMatrix, tauGrid(index));
        dominantRealHz(index) = real(dominantZero);
        dominantImaginaryHz(index) = abs(imag(dominantZero));
    end

    crossingIndex = find( ...
        dominantRealHz(1:end-1) <= 0 & dominantRealHz(2:end) > 0, 1, 'first');
    if isempty(crossingIndex)
        criticalTau = NaN;
        criticalZeroHz = NaN + 1i*NaN;
    else
        lowerTau = tauGrid(crossingIndex);
        upperTau = tauGrid(crossingIndex + 1);
        for iteration = 1:45
            middleTau = (lowerTau + upperTau) / 2;
            middleZero = dominantZeroAtTau( ...
                data.converterMatrix, data.networkMatrix, middleTau);
            if real(middleZero) > 0
                upperTau = middleTau;
            else
                lowerTau = middleTau;
            end
        end
        criticalTau = (lowerTau + upperTau) / 2;
        criticalZeroHz = dominantZeroAtTau( ...
            data.converterMatrix, data.networkMatrix, criticalTau);
    end

    finalZeroHz = dominantZeroAtTau( ...
        data.converterMatrix, data.networkMatrix, 1);
    summary = struct( ...
        'caseName', caseName, ...
        'criticalTau', criticalTau, ...
        'criticalZeroRealHz', real(criticalZeroHz), ...
        'criticalOscillationHz', abs(imag(criticalZeroHz)), ...
        'finalDominantZeroRealHz', real(finalZeroHz), ...
        'finalDominantOscillationHz', abs(imag(finalZeroHz)));

    continuationTable = table( ...
        tauGrid, dominantRealHz, dominantImaginaryHz, ...
        'VariableNames', {'tau', 'dominant_zero_real_Hz', ...
        'dominant_zero_oscillation_Hz'});
    writetable(continuationTable, ...
        fullfile(outputRoot, 'return_zero_continuation.csv'));
    writelines(jsonencode(summary, PrettyPrint=true), ...
        fullfile(outputRoot, 'return_zero_continuation_summary.json'));

    fprintf(['ZERO_CONTINUATION case=%s critical_tau=%.12g ', ...
        'critical_f=%.12gHz final_zero=%.12g+j%.12gHz\n'], ...
        caseName, criticalTau, abs(imag(criticalZeroHz)), ...
        real(finalZeroHz), abs(imag(finalZeroHz)));
end

function dominantZeroHz = dominantZeroAtTau(converterMatrix, networkMatrix, tau)
    characteristicMatrix = minreal(networkMatrix + tau * converterMatrix);
    zerosHz = tzero(ss(characteristicMatrix)) / (2*pi);
    [~, dominantIndex] = max(real(zerosHz));
    dominantZeroHz = zerosHz(dominantIndex);
end
