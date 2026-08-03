classdef evaluateMixedGainPhaseSamplesTest < matlab.unittest.TestCase
    %EVALUATEMIXEDGAINPHASESAMPLESTEST Sampled mixed-condition logic.

    methods (TestClassSetup)
        function addSourceFolder(testCase)
            projectRoot = fileparts(fileparts(mfilename('fullpath')));
            testCase.applyFixture(matlab.unittest.fixtures.PathFixture( ...
                fullfile(projectRoot, 'src')));
        end
    end

    methods (Test, TestTags = {'Unit'})
        function testGainPassCoversNonsectorialConverter(testCase)
            converters = {0.1*diag([1, -1])};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyEqual(result.gainStatus, "pass");
            testCase.verifyEqual(result.sampleCoverage, "gain-pass");
            testCase.verifyEqual(result.sampledBandStatus, ...
                "confirmed-on-grid");
        end

        function testPhasePassCoversGainFailure(testCase)
            converters = {2*exp(0.2i)*eye(2)};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyEqual(result.gainStatus, "fail");
            testCase.verifyEqual(result.phaseStatus, "pass");
            testCase.verifyEqual(result.sampleCoverage, "phase-pass");
        end

        function testBothConditionsPass(testCase)
            result = testCase.evaluate({0.5*eye(2)}, eye(2));

            testCase.verifyEqual(result.sampleCoverage, "both-pass");
        end

        function testClearFailureDoesNotClaimInstability(testCase)
            phases = [0, 2*pi/3, -2*pi/3];
            converter = 2*diag(exp(1i*phases));

            result = testCase.evaluate({converter}, eye(3));

            testCase.verifyEqual(result.sampleCoverage, "uncovered");
            testCase.verifyEqual(result.sampledBandStatus, ...
                "not-confirmed-on-grid");
            testCase.verifyEqual(result.theoremStatus, ...
                "not-confirmed-by-sufficient-condition");
            testCase.verifySubstring(result.interpretationBoundary, ...
                "does not mean");
        end

        function testCrossConverterPhaseSpreadIsEnforced(testCase)
            converters = {2*exp(0.6i*pi), 2*exp(-0.6i*pi)};

            result = testCase.evaluate(converters, eye(2));

            testCase.verifyLessThan(result.converterPhaseSpreadMargin, 0);
            testCase.verifyEqual(result.phaseStatus, "fail");
            testCase.verifyEqual(result.sampleCoverage, "uncovered");
            testCase.verifyTrue(any(result.reasonCodes{1} == ...
                "converter-phase-spread-overlap"));
        end

        function testFiniteGridPassDoesNotCompleteTheorem(testCase)
            preconditions = testCase.completePreconditions();
            preconditions.fullFrequencyCoverage = false;

            result = testCase.evaluate( ...
                {0.5*eye(2)}, eye(2), preconditions);

            testCase.verifyEqual(result.sampledBandStatus, ...
                "confirmed-on-grid");
            testCase.verifyEqual(result.theoremStatus, "indeterminate");
        end

        function testCompleteDeclaredPreconditionsAllowTheoremStatus(testCase)
            result = testCase.evaluate({0.5*eye(2)}, eye(2), ...
                testCase.completePreconditions());

            testCase.verifyEqual(result.theoremStatus, ...
                "confirmed-by-sufficient-condition");
        end

        function testIllConditionedNetworkMakesUncoveredPhasePending(testCase)
            converters = {2*eye(2)};
            network = diag([1, 1e-14]);

            result = testCase.evaluate(converters, network);

            testCase.verifyEqual(result.gainStatus, "fail");
            testCase.verifyEqual(result.phaseStatus, "indeterminate");
            testCase.verifyEqual(result.sampleCoverage, "indeterminate");
        end

        function testMultipleFrequencySamplesRetainIndividualCoverage(testCase)
            converters = {cat(3, 0.5*eye(2), 2*exp(0.2i)*eye(2))};
            network = cat(3, eye(2), eye(2));

            result = evaluateMixedGainPhaseSamples( ...
                converters, network, [1, 2], testCase.conventions(), ...
                testCase.incompletePreconditions(), struct());

            testCase.verifyEqual(result.sampleCoverage, ...
                ["both-pass", "phase-pass"]);
            testCase.verifyEqual(result.sampledBandStatus, ...
                "confirmed-on-grid");
        end
    end

    methods (Access=private)
        function result = evaluate(testCase, converters, network, preconditions)
            if nargin < 4
                preconditions = testCase.incompletePreconditions();
            end
            result = evaluateMixedGainPhaseSamples(converters, network, 1, ...
                testCase.conventions(), preconditions, struct());
        end

        function value = conventions(~)
            value = struct( ...
                'frameConventionId', "analytic-test-dq", ...
                'currentDirection', "converter-to-network", ...
                'powerDirection', "injection-positive", ...
                'sBase', 1, ...
                'vBase', 1, ...
                'fBase', 50, ...
                'matrixType', "admittance", ...
                'globalFrameId', "test-global-dq");
        end

        function value = incompletePreconditions(testCase)
            value = testCase.completePreconditions();
            value.endpointsCovered = false;
            value.fullFrequencyCoverage = false;
        end

        function value = completePreconditions(~)
            value = struct( ...
                'openLoopStable', true, ...
                'realRationalProper', true, ...
                'transformationWellDefined', true, ...
                'networkInverseStable', true, ...
                'noRhpCancellation', true, ...
                'endpointsCovered', true, ...
                'fullFrequencyCoverage', true);
        end
    end
end
