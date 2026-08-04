classdef authorFig8RawFixtureTest < matlab.unittest.TestCase
    %AUTHORFIG8RAWFIXTURETEST Clean-clone checks for the tracked fixture.

    methods (Test, TestTags = {'Integration'})
        function testControlledCasesAndManifestAreConsistent(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            fixtureRoot = fullfile(projectRoot, 'experiments', ...
                'baseline', 'fixtures');
            response = readtable(fullfile(fixtureRoot, ...
                'author_fig8_raw_frequency_response.csv'), ...
                TextType='string');
            spectrum = readtable(fullfile(fixtureRoot, ...
                'author_fig8_spectrum.csv'), TextType='string');
            manifest = jsondecode(fileread(fullfile(fixtureRoot, ...
                'author_fig8_fixture_manifest.json')));

            caseIds = ["fig8_D_0p05", "fig8_D_0p5"];
            testCase.verifyEqual(unique(response.case_id, 'stable'), ...
                caseIds.');
            testCase.verifyEqual(height(response), 2000);
            numericNames = string(response.Properties.VariableNames(2:end));
            for index = 1:numel(numericNames)
                testCase.verifyTrue(all(isfinite(response.(numericNames(index)))));
            end

            low = response(response.case_id == caseIds(1), :);
            high = response(response.case_id == caseIds(2), :);
            testCase.verifyEqual(height(low), 1000);
            testCase.verifyEqual(height(high), 1000);
            testCase.verifyTrue(all(diff(low.frequency_Hz) > 0));
            testCase.verifyEqual(high.frequency_Hz, low.frequency_Hz, ...
                RelTol=1e-14);
            testCase.verifyEqual(unique(low.damping_D), 0.05, ...
                AbsTol=1e-12);
            testCase.verifyEqual(unique(high.damping_D), 0.5, ...
                AbsTol=1e-12);
            networkNames = startsWith(string( ...
                response.Properties.VariableNames), "Ynet");
            testCase.verifyEqual(high{:, networkNames}, ...
                low{:, networkNames}, AbsTol=1e-13);

            poleRows = spectrum(spectrum.value_type == ...
                "closed-loop-pole" & logical(spectrum.is_dominant_pair), :);
            lowPoleReal = max(poleRows.real_Hz( ...
                poleRows.case_id == caseIds(1)));
            highPoleReal = max(poleRows.real_Hz( ...
                poleRows.case_id == caseIds(2)));
            testCase.verifyGreaterThan(lowPoleReal, 0);
            testCase.verifyLessThan(highPoleReal, 0);

            testCase.verifyEqual(manifest.frequencyResponseRowCount, ...
                height(response));
            testCase.verifyEqual(manifest.spectrumRowCount, height(spectrum));
            testCase.verifyEqual(manifest.frequencyGrid.pointCountPerCase, ...
                1000);
            testCase.verifyEqual(string(manifest.caseIds), caseIds.');
            testCase.verifyEqual( ...
                string(manifest.portConventions.powerConvention), ...
                "load-positive");
            testCase.verifyEqual(string(manifest.simplusProvenance.commit), ...
                "unavailable-local-snapshot");
        end
    end
end
