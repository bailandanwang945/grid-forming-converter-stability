function fixturePath = export_author_inf_bus_frequency_fixture()
%EXPORT_AUTHOR_INF_BUS_FREQUENCY_FIXTURE Pin author baseline responses.
%   This provenance helper requires the ignored baseline MAT workspaces.
%   The main geometry experiment reads only the resulting tracked CSV.

    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    fixtureRoot = fullfile(projectRoot, 'experiments', 'geometry', 'fixtures');
    fixturePath = fullfile(fixtureRoot, ...
        'author_inf_bus_converter_frequency_response.csv');
    caseNames = ["stable", "unstable"];
    frequenciesHz = logspace(log10(0.1), log10(5), 81).';
    tables = cell(numel(caseNames), 1);

    for caseIndex = 1:numel(caseNames)
        caseName = caseNames(caseIndex);
        workspacePath = fullfile(projectRoot, 'results', 'baseline', ...
            caseName, 'baseline_workspace.mat');
        assert(isfile(workspacePath), 'Geometry:MissingBaseline', ...
            'Run the author infinite-bus baseline before exporting.');
        baseline = load(workspacePath, 'Yc');
        tables{caseIndex} = evaluateResponse( ...
            baseline.Yc, caseName, frequenciesHz);
    end

    if ~isfolder(fixtureRoot)
        mkdir(fixtureRoot);
    end
    writetable(vertcat(tables{:}), fixturePath);
    fprintf('GEOMETRY_FIXTURE rows=%d path=%s\n', ...
        numel(caseNames)*numel(frequenciesHz), fixturePath);
end

function responseTable = evaluateResponse(Yc, caseName, frequenciesHz)
    pointCount = numel(frequenciesHz);
    response = complex(zeros(2, 2, pointCount));
    for index = 1:pointCount
        response(:, :, index) = evalfr(Yc, 1i*2*pi*frequenciesHz(index));
    end

    caseColumn = repmat(caseName, pointCount, 1);
    responseTable = table(caseColumn, frequenciesHz, ...
        real(squeeze(response(1, 1, :))), imag(squeeze(response(1, 1, :))), ...
        real(squeeze(response(1, 2, :))), imag(squeeze(response(1, 2, :))), ...
        real(squeeze(response(2, 1, :))), imag(squeeze(response(2, 1, :))), ...
        real(squeeze(response(2, 2, :))), imag(squeeze(response(2, 2, :))), ...
        'VariableNames', {'case_name', 'frequency_Hz', ...
        'Y11_real', 'Y11_imag', 'Y12_real', 'Y12_imag', ...
        'Y21_real', 'Y21_imag', 'Y22_real', 'Y22_imag'});
end
