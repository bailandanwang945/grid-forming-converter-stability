function fixture = load_author_fig8_raw_fixture(fixtureRoot)
%LOAD_AUTHOR_FIG8_RAW_FIXTURE Load tracked raw responses into matrix arrays.

    if nargin < 1 || isempty(fixtureRoot)
        fixtureRoot = fullfile(fileparts(mfilename('fullpath')), 'fixtures');
    end
    response = readtable(fullfile(fixtureRoot, ...
        'author_fig8_raw_frequency_response.csv'), TextType='string');
    spectrum = readtable(fullfile(fixtureRoot, ...
        'author_fig8_spectrum.csv'), TextType='string');
    manifest = jsondecode(fileread(fullfile(fixtureRoot, ...
        'author_fig8_fixture_manifest.json')));
    caseIds = string(manifest.caseIds(:));
    cases = repmat(struct(), numel(caseIds), 1);
    for caseIndex = 1:numel(caseIds)
        caseId = caseIds(caseIndex);
        caseRows = response(response.case_id == caseId, :);
        cases(caseIndex).caseId = caseId;
        cases(caseIndex).damping = caseRows.damping_D(1);
        cases(caseIndex).frequenciesHz = caseRows.frequency_Hz;
        cases(caseIndex).converterResponse = matrixResponse(caseRows, "Yc");
        cases(caseIndex).networkResponse = matrixResponse(caseRows, "Ynet");
        cases(caseIndex).spectrum = spectrum(spectrum.case_id == caseId, :);
    end
    operatingPoint = manifest.derivedOperatingPoint;
    fixture = struct( ...
        'cases', cases, ...
        'operatingPoint', struct('vd', operatingPoint.vd, ...
            'vq', operatingPoint.vq, 'id', operatingPoint.id, ...
            'iq', operatingPoint.iq), ...
        'baseAngularFrequency', manifest.baseAngularFrequency, ...
        'manifest', manifest);
end

function response = matrixResponse(rows, prefix)
    pointCount = height(rows);
    response = complex(zeros(2, 2, pointCount));
    response(1, 1, :) = complex(rows.(prefix+"11_real"), ...
        rows.(prefix+"11_imag"));
    response(1, 2, :) = complex(rows.(prefix+"12_real"), ...
        rows.(prefix+"12_imag"));
    response(2, 1, :) = complex(rows.(prefix+"21_real"), ...
        rows.(prefix+"21_imag"));
    response(2, 2, :) = complex(rows.(prefix+"22_real"), ...
        rows.(prefix+"22_imag"));
end
