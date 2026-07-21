function summary = run_inf_bus_damping_grid_boundary()
%RUN_INF_BUS_DAMPING_GRID_BOUNDARY Track the D-grid-strength Hopf boundary.
%   The Fig. 8 line impedance is multiplied by kappa while preserving X/R.
%   At each kappa, a predictor-corrector step locates the critical VSM
%   damping. The predictor uses the implicit characteristic-zero tangent
%
%       dD/dkappa = -Re(ds/dkappa) / Re(ds/dD),
%
%   where ds/dp is obtained from left/right null vectors of the port
%   characteristic matrix M(s,D,kappa) = Ynet(s,kappa) + Yc(s,D,kappa).

    projectRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    authorRoot = fullfile(projectRoot, 'external', 'cifelli-small-gain-phase');
    simplusRoot = fullfile(projectRoot, 'external', 'simplus-grid-tool');
    outputRoot = fullfile(projectRoot, 'results', 'schur', ...
        'damping-grid-boundary');
    runtimeRoot = fullfile(projectRoot, 'tmp', 'damping-grid-boundary', ...
        'runtime-simplus-grid-tool');
    inputName = 'UserData_inf_bus_Fig_8.xlsm';

    oldPath = path;
    oldFolder = pwd;
    oldFigureVisibility = get(groot, 'defaultFigureVisible');
    cleanup = onCleanup(@() restoreEnvironment( ...
        oldPath, oldFolder, oldFigureVisibility, runtimeRoot)); %#ok<NASGU>

    prepareRuntimeTool(simplusRoot, authorRoot, runtimeRoot, inputName);
    path(oldPath);
    rmpathIfPresent(genpath(simplusRoot));
    addpath(genpath(runtimeRoot), '-begin');
    addpath(authorRoot, '-begin');
    set(groot, 'defaultFigureVisible', 'off');
    cd(runtimeRoot);
    rehash;

    resolvedClass = which('SimplusGT.Class.GridFormingVSI');
    expectedClass = fullfile(runtimeRoot, '+SimplusGT', '+Class', ...
        'GridFormingVSI.m');
    assert(strcmpi(resolvedClass, expectedClass), ...
        'GridBoundary:WrongClass', 'The isolated author class was not resolved.');

    UserDataName = 'UserData'; %#ok<NASGU>
    UserDataType = 1; %#ok<NASGU>
    NumApparatus = NaN; %#ok<NASGU>
    ApparatusType = {}; %#ok<NASGU>
    Para = {}; %#ok<NASGU>
    SimplusGT.Toolbox.Main();

    assert(NumApparatus == 2 && ApparatusType{2} == 20, ...
        'GridBoundary:UnexpectedSystem', ...
        'The input is not the expected GFM-infinite-bus system.');
    assert(abs(Para{2}.Dw - 0.05) < 1e-12, ...
        'GridBoundary:UnexpectedInitialDamping', ...
        'Fig. 8 workbook no longer has Para.Dw = 0.05.');

    base = struct( ...
        'listBus', ListBus, ...
        'listLine', ListLine, ...
        'wbase', Wbase, ...
        'sampleTime', Ts, ...
        'advance', Advance, ...
        'apparatusBus', {ApparatusBus}, ...
        'apparatusType', {ApparatusType}, ...
        'para', {Para}, ...
        'numberOfBuses', NumBus);
    baseMutualRows = base.listLine(:, 1) ~= base.listLine(:, 2);
    baseLineR = base.listLine(baseMutualRows, 3);
    baseLineWL = base.listLine(baseMutualRows, 4);
    assert(isscalar(baseLineR) && isscalar(baseLineWL), ...
        'GridBoundary:UnexpectedNetwork', ...
        'The prototype expects one mutual line in the infinite-bus case.');

    kappaGrid = (0.5:0.1:1.5).';
    pointCount = numel(kappaGrid);
    criticalDamping = zeros(pointCount, 1);
    criticalPoleRealHz = zeros(pointCount, 1);
    criticalFrequencyHz = zeros(pointCount, 1);
    criticalZeroRealHz = zeros(pointCount, 1);
    poleZeroMismatchHz = zeros(pointCount, 1);
    scr = zeros(pointCount, 1);
    tangentDPerKappa = zeros(pointCount, 1);
    realPoleSensitivityD = zeros(pointCount, 1);
    realPoleSensitivityKappa = zeros(pointCount, 1);
    predictedDamping = NaN(pointCount, 1);
    predictorError = NaN(pointCount, 1);
    nullResidual = zeros(pointCount, 1);

    previousDamping = NaN;
    previousTangent = NaN;
    for index = 1:pointCount
        kappa = kappaGrid(index);
        context = createContext(base, kappa);
        if index == 1
            predictedDamping(index) = 0.05;
        else
            deltaKappa = kappa - kappaGrid(index - 1);
            predictedDamping(index) = previousDamping + ...
                previousTangent * deltaKappa;
        end

        [criticalDamping(index), criticalPoint] = correctBoundary( ...
            context, predictedDamping(index));
        sensitivity = characteristicSensitivity( ...
            base, context, criticalDamping(index), kappa, criticalPoint);

        criticalPoleRealHz(index) = real(criticalPoint.dominantPoleHz);
        criticalFrequencyHz(index) = abs(imag(criticalPoint.dominantPoleHz));
        criticalZeroRealHz(index) = real(criticalPoint.dominantReturnZeroHz);
        poleZeroMismatchHz(index) = abs(criticalPoint.dominantPoleHz - ...
            criticalPoint.dominantReturnZeroHz);
        scr(index) = 1 / (kappa * hypot(baseLineR, baseLineWL));
        tangentDPerKappa(index) = sensitivity.dDampingDkappa;
        realPoleSensitivityD(index) = real(sensitivity.dsDampingHz);
        realPoleSensitivityKappa(index) = real(sensitivity.dsKappaHz);
        nullResidual(index) = sensitivity.sigmaMin;
        if index > 1
            predictorError(index) = predictedDamping(index) - ...
                criticalDamping(index);
        end

        previousDamping = criticalDamping(index);
        previousTangent = tangentDPerKappa(index);
        fprintf(['GRID_BOUNDARY kappa=%.3f SCR=%.6f Dcrit=%.9f ', ...
            'f=%.6fHz tangent=%.6f predictor_error=%.3g\n'], ...
            kappa, scr(index), criticalDamping(index), ...
            criticalFrequencyHz(index), tangentDPerKappa(index), ...
            predictorError(index));
    end

    if ~isfolder(outputRoot)
        mkdir(outputRoot);
    end
    centralDifferenceTangent = NaN(pointCount, 1);
    tangentRelativeError = NaN(pointCount, 1);
    for index = 2:pointCount-1
        centralDifferenceTangent(index) = ...
            (criticalDamping(index + 1) - criticalDamping(index - 1)) / ...
            (kappaGrid(index + 1) - kappaGrid(index - 1));
        tangentRelativeError(index) = abs( ...
            tangentDPerKappa(index) - centralDifferenceTangent(index)) / ...
            abs(centralDifferenceTangent(index));
    end
    boundaryTable = table(kappaGrid, scr, criticalDamping, ...
        criticalPoleRealHz, criticalFrequencyHz, criticalZeroRealHz, ...
        poleZeroMismatchHz, tangentDPerKappa, realPoleSensitivityD, ...
        realPoleSensitivityKappa, predictedDamping, predictorError, ...
        centralDifferenceTangent, tangentRelativeError, nullResidual, ...
        'VariableNames', {'impedance_scale_kappa', 'SCR', ...
        'critical_damping_D', 'critical_pole_real_Hz', ...
        'critical_frequency_Hz', 'critical_return_zero_real_Hz', ...
        'pole_zero_mismatch_Hz', 'dDcrit_dkappa', ...
        'dRealPole_dD_Hz', 'dRealPole_dkappa_Hz', ...
        'predicted_damping_D', 'predictor_error_D', ...
        'central_difference_dDcrit_dkappa', ...
        'tangent_relative_error', ...
        'characteristic_sigma_min'});
    writetable(boundaryTable, fullfile(outputRoot, 'boundary.csv'));

    maximumPredictorError = max(abs(predictorError), [], 'omitnan');
    maximumTangentRelativeError = max(tangentRelativeError, [], 'omitnan');
    maximumPoleZeroMismatch = max(poleZeroMismatchHz);
    maximumNullResidual = max(nullResidual);
    summary = struct( ...
        'inputWorkbook', ...
            "external/cifelli-small-gain-phase/" + string(inputName), ...
        'impedanceScaling', 'R = kappa*0.5 pu, wL = kappa*1 pu', ...
        'scrDefinition', 'SCR = 1/abs(R+j*wL) on the selected pu base', ...
        'kappaMinimum', min(kappaGrid), ...
        'kappaMaximum', max(kappaGrid), ...
        'scrMinimum', min(scr), ...
        'scrMaximum', max(scr), ...
        'criticalDampingMinimum', min(criticalDamping), ...
        'criticalDampingMaximum', max(criticalDamping), ...
        'criticalFrequencyMinimumHz', min(criticalFrequencyHz), ...
        'criticalFrequencyMaximumHz', max(criticalFrequencyHz), ...
        'maximumPredictorErrorD', maximumPredictorError, ...
        'maximumTangentRelativeError', maximumTangentRelativeError, ...
        'maximumPoleZeroMismatchHz', maximumPoleZeroMismatch, ...
        'maximumCharacteristicSigmaMin', maximumNullResidual);
    writelines(jsonencode(summary, PrettyPrint=true), ...
        fullfile(outputRoot, 'summary.json'));
    save(fullfile(outputRoot, 'boundary_workspace.mat'), ...
        'boundaryTable', 'summary');

    fprintf(['GRID_BOUNDARY_DONE max_predictor_error=%.6g ', ...
        'max_pole_zero_mismatch=%.3gHz\n'], ...
        maximumPredictorError, maximumPoleZeroMismatch);
end

function context = createContext(base, kappa)
    listLine = base.listLine;
    mutualRows = listLine(:, 1) ~= listLine(:, 2);
    listLine(mutualRows, 3:4) = kappa * base.listLine(mutualRows, 3:4);

    switch base.advance.PowerFlowAlgorithm
        case 1
            powerFlow = SimplusGT.PowerFlow.PowerFlowGS( ...
                base.listBus, listLine, base.wbase);
        case 2
            powerFlow = SimplusGT.PowerFlow.PowerFlowNR( ...
                base.listBus, listLine, base.wbase);
        otherwise
            error('GridBoundary:PowerFlowAlgorithm', ...
                'Unsupported power-flow algorithm.');
    end
    [listBusNew, listLineNew, powerFlowNew] = ...
        SimplusGT.PowerFlow.Load2SelfBranch( ...
        base.listBus, listLine, powerFlow);
    [objectYbus, ybusDss] = SimplusGT.Toolbox.YbusCalcDss( ...
        listBusNew, listLineNew, base.wbase);
    objectZbus = SimplusGT.ObjSwitchInOut(objectYbus, length(ybusDss));
    [~, networkMatrix] = objectYbus.GetDSS(objectYbus);
    networkMatrix = networkMatrix(3:end, 3:end);

    apparatusPowerFlow = cell(size(base.apparatusType));
    objectTemplate = cell(size(base.apparatusType));
    for apparatusIndex = 1:numel(base.apparatusType)
        bus = base.apparatusBus{apparatusIndex};
        apparatusPowerFlow{apparatusIndex} = powerFlowNew{bus};
        objectTemplate{apparatusIndex} = ...
            SimplusGT.Toolbox.ApparatusModelCreate( ...
            bus, base.apparatusType{apparatusIndex}, ...
            apparatusPowerFlow{apparatusIndex}, ...
            base.para{apparatusIndex}, base.sampleTime, ...
            listBusNew, base.advance);
    end

    context = struct( ...
        'kappa', kappa, ...
        'listBusNew', listBusNew, ...
        'networkMatrix', networkMatrix, ...
        'objectZbus', objectZbus, ...
        'apparatusPowerFlow', {apparatusPowerFlow}, ...
        'objectTemplate', {objectTemplate}, ...
        'base', base);
end

function [criticalDamping, criticalPoint] = correctBoundary(context, prediction)
    prediction = max(prediction, 1e-5);
    halfWidth = 0.02;
    lowerDamping = max(1e-6, prediction - halfWidth);
    upperDamping = prediction + halfWidth;
    lowerPoint = evaluatePoint(context, lowerDamping, false);
    upperPoint = evaluatePoint(context, upperDamping, false);

    expansion = 0;
    while real(lowerPoint.dominantPoleHz) <= 0 && expansion < 12
        lowerDamping = max(1e-6, lowerDamping - halfWidth);
        lowerPoint = evaluatePoint(context, lowerDamping, false);
        halfWidth = 1.5 * halfWidth;
        expansion = expansion + 1;
        if lowerDamping == 1e-6
            break;
        end
    end
    expansion = 0;
    while real(upperPoint.dominantPoleHz) > 0 && expansion < 12
        upperDamping = upperDamping + halfWidth;
        upperPoint = evaluatePoint(context, upperDamping, false);
        halfWidth = 1.5 * halfWidth;
        expansion = expansion + 1;
    end
    assert(real(lowerPoint.dominantPoleHz) > 0 && ...
        real(upperPoint.dominantPoleHz) <= 0, ...
        'GridBoundary:NoBracket', ...
        'Could not bracket the stability boundary near D = %.6g.', prediction);

    for iteration = 1:27
        middleDamping = (lowerDamping + upperDamping) / 2;
        middlePoint = evaluatePoint(context, middleDamping, false);
        if real(middlePoint.dominantPoleHz) > 0
            lowerDamping = middleDamping;
        else
            upperDamping = middleDamping;
        end
    end
    criticalDamping = (lowerDamping + upperDamping) / 2;
    criticalPoint = evaluatePoint(context, criticalDamping, true);
end

function point = evaluatePoint(context, damping, calculateZero)
    converterIndex = 2;
    [converterObject, converterDss] = converterAt( ...
        context, damping);
    objects = context.objectTemplate;
    objects{converterIndex} = converterObject;
    linkedObject = SimplusGT.Toolbox.ApparatusModelLink(objects);
    [systemDssObject, systemDss] = SimplusGT.Toolbox.ConnectGmZbus( ...
        linkedObject, context.objectZbus, context.base.numberOfBuses);
    assert(isproper(systemDss), 'GridBoundary:ImproperSystem', ...
        'The system is improper at kappa = %.6g, D = %.6g.', ...
        context.kappa, damping);
    systemSsObject = SimplusGT.ObjDss2Ss(systemDssObject);
    [~, systemSs] = systemSsObject.GetSS(systemSsObject);
    polesHz = eig(systemSs.A) / (2*pi);
    polesHz = polesHz(abs(polesHz) > 1e-7);
    [~, dominantIndex] = max(real(polesHz));
    dominantPoleHz = polesHz(dominantIndex);

    dominantReturnZeroHz = NaN + 1i*NaN;
    if calculateZero
        characteristic = context.networkMatrix + converterDss(1:2, 1:2);
        zerosHz = tzero(ss(minreal(characteristic))) / (2*pi);
        zerosHz = zerosHz(abs(zerosHz) > 1e-7);
        [~, zeroIndex] = max(real(zerosHz));
        dominantReturnZeroHz = zerosHz(zeroIndex);
    end
    point = struct( ...
        'damping', damping, ...
        'dominantPoleHz', dominantPoleHz, ...
        'dominantReturnZeroHz', dominantReturnZeroHz, ...
        'converterDss', converterDss);
end

function [converterObject, converterDss] = converterAt(context, damping)
    converterIndex = 2;
    para = context.base.para{converterIndex};
    para.Dw = damping;
    [converterObject, converterDss] = ...
        SimplusGT.Toolbox.ApparatusModelCreate( ...
        context.base.apparatusBus{converterIndex}, ...
        context.base.apparatusType{converterIndex}, ...
        context.apparatusPowerFlow{converterIndex}, para, ...
        context.base.sampleTime, context.listBusNew, context.base.advance);
end

function sensitivity = characteristicSensitivity( ...
        base, context, damping, kappa, criticalPoint)

    criticalS = 2*pi*criticalPoint.dominantPoleHz;
    dampingStep = 1e-5;
    kappaStep = 1e-4;
    sStep = 1e-5;

    matrix = characteristicAt(context, damping, criticalS);
    matrixDPlus = characteristicAt(context, damping + dampingStep, criticalS);
    matrixDMinus = characteristicAt(context, damping - dampingStep, criticalS);
    derivativeDamping = (matrixDPlus - matrixDMinus) / (2*dampingStep);

    contextKPlus = createContext(base, kappa + kappaStep);
    contextKMinus = createContext(base, kappa - kappaStep);
    matrixKPlus = characteristicAt(contextKPlus, damping, criticalS);
    matrixKMinus = characteristicAt(contextKMinus, damping, criticalS);
    derivativeKappa = (matrixKPlus - matrixKMinus) / (2*kappaStep);

    matrixSPlus = characteristicAt(context, damping, criticalS + sStep);
    matrixSMinus = characteristicAt(context, damping, criticalS - sStep);
    derivativeS = (matrixSPlus - matrixSMinus) / (2*sStep);

    [leftVectors, singularValues, rightVectors] = svd(matrix);
    leftVector = leftVectors(:, end);
    rightVector = rightVectors(:, end);
    denominator = leftVector' * derivativeS * rightVector;
    dsDamping = -(leftVector' * derivativeDamping * rightVector) / denominator;
    dsKappa = -(leftVector' * derivativeKappa * rightVector) / denominator;
    dampingTangent = -real(dsKappa) / real(dsDamping);

    sensitivity = struct( ...
        'dsDampingHz', dsDamping/(2*pi), ...
        'dsKappaHz', dsKappa/(2*pi), ...
        'dDampingDkappa', dampingTangent, ...
        'sigmaMin', singularValues(end, end));
end

function matrix = characteristicAt(context, damping, s)
    [~, converterDss] = converterAt(context, damping);
    matrix = evalfr(context.networkMatrix + converterDss(1:2, 1:2), s);
end

function prepareRuntimeTool(simplusRoot, authorRoot, runtimeRoot, inputName)
    if isfolder(runtimeRoot)
        rmdir(runtimeRoot, 's');
    end
    [copyStatus, copyMessage] = copyfile(simplusRoot, runtimeRoot);
    assert(copyStatus, 'GridBoundary:CopySimplusFailed', '%s', copyMessage);
    [copyStatus, copyMessage] = copyfile( ...
        fullfile(authorRoot, 'GridFormingVSI.m'), ...
        fullfile(runtimeRoot, '+SimplusGT', '+Class', 'GridFormingVSI.m'), 'f');
    assert(copyStatus, 'GridBoundary:CopyClassFailed', '%s', copyMessage);
    [copyStatus, copyMessage] = copyfile( ...
        fullfile(authorRoot, inputName), fullfile(runtimeRoot, 'UserData.xlsm'), 'f');
    assert(copyStatus, 'GridBoundary:CopyInputFailed', '%s', copyMessage);
    jsonPath = fullfile(runtimeRoot, 'UserData.json');
    if isfile(jsonPath)
        delete(jsonPath);
    end
end

function rmpathIfPresent(pathText)
    pathParts = split(string(pathText), pathsep);
    activeParts = split(string(path), pathsep);
    removableParts = pathParts(ismember(lower(pathParts), lower(activeParts)));
    if ~isempty(removableParts)
        rmpath(char(join(removableParts, pathsep)));
    end
end

function restoreEnvironment(oldPath, oldFolder, oldFigureVisibility, runtimeRoot)
    path(oldPath);
    cd(oldFolder);
    set(groot, 'defaultFigureVisible', oldFigureVisibility);
    close all force;
    if isfolder(runtimeRoot)
        rmdir(runtimeRoot, 's');
    end
end
