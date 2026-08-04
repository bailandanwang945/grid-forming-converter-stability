classdef buildVirtualImpedanceWeightingSamplesTest < matlab.unittest.TestCase
    %BUILDVIRTUALIMPEDANCEWEIGHTINGSAMPLESTEST Author weighting tests.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testAuthorZeroFrequencyMatrix(testCase)
            configuration = testCase.authorConfiguration();
            expectedNormalization = hypot(0.01, 0.1);
            expected = [0.01, -0.1; 0.1, 0.01]/expectedNormalization;

            result = buildVirtualImpedanceWeightingSamples( ...
                [0, 50], configuration);

            testCase.verifyEqual(result.responses(:, :, 1), expected, ...
                AbsTol=1e-14);
            testCase.verifyEqual( ...
                result.normalization, expectedNormalization, AbsTol=1e-14);
        end

        function testAuthorBaseFrequencyMatrix(testCase)
            configuration = testCase.authorConfiguration();
            expectedNormalization = hypot(0.01, 0.1);
            expected = [0.01+0.1i, -0.1; ...
                0.1, 0.01+0.1i]/expectedNormalization;

            result = buildVirtualImpedanceWeightingSamples( ...
                [0, 50], configuration);

            testCase.verifyEqual(result.responses(:, :, 2), expected, ...
                AbsTol=1e-14);
        end

        function testInductanceUsesBaseAngularFrequency(testCase)
            configuration = testCase.authorConfiguration();

            result = buildVirtualImpedanceWeightingSamples( ...
                [0, 50], configuration);

            testCase.verifyEqual(result.inductance, ...
                0.1/(2*pi*50), AbsTol=1e-16);
        end

        function testNormalizationCanBeDisabled(testCase)
            configuration = testCase.authorConfiguration();
            configuration.NormalizeAtBase = false;

            result = buildVirtualImpedanceWeightingSamples( ...
                [0, 50], configuration);

            testCase.verifyEqual(result.responses(:, :, 1), ...
                [0.01, -0.1; 0.1, 0.01], AbsTol=1e-14);
            testCase.verifyEqual(result.normalization, 1, AbsTol=0);
        end

        function testZeroNormalizedImpedanceIsRejected(testCase)
            configuration = testCase.authorConfiguration();
            configuration.VirtualResistance = 0;
            configuration.VirtualReactance = 0;

            testCase.verifyError( ...
                @() buildVirtualImpedanceWeightingSamples(0, configuration), ...
                'gfm:buildVirtualImpedanceWeightingSamples:ZeroNormalization');
        end

        function testInvalidBaseFrequencyIsRejected(testCase)
            configuration = testCase.authorConfiguration();
            configuration.BaseAngularFrequency = 0;

            testCase.verifyError( ...
                @() buildVirtualImpedanceWeightingSamples(0, configuration), ...
                'gfm:buildVirtualImpedanceWeightingSamples:InvalidField');
        end
    end

    methods (Static, Access=private)
        function configuration = authorConfiguration()
            configuration = struct( ...
                'BaseAngularFrequency', 2*pi*50, ...
                'VirtualResistance', 0.01, ...
                'VirtualReactance', 0.1, ...
                'NormalizeAtBase', true);
        end
    end
end
